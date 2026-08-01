import { createHash } from "node:crypto";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();
const SITEMAP_URL = "https://help.shopee.vn/sitemap.xml";
const SNAPSHOT_DATE = new Date(process.env.KB_SNAPSHOT_DATE || "2026-07-29T00:00:00.000Z");
const MAX_PAGES = Number(process.env.KB_MAX_PAGES || 0);
const CONCURRENCY = Number(process.env.KB_CRAWL_CONCURRENCY || 2);

const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const decodeEntities = (value) => value
  .replace(/&nbsp;|&#160;/gi, " ")
  .replace(/&amp;/gi, "&")
  .replace(/&lt;/gi, "<")
  .replace(/&gt;/gi, ">")
  .replace(/&quot;/gi, '"')
  .replace(/&#39;|&apos;/gi, "'")
  .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)));

function stripHtml(html) {
  return decodeEntities(html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<\/(p|li|h[1-6]|tr|div|section)>/gi, "\n")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, " "))
    .replace(/[ \t]+/g, " ")
    .replace(/\n\s*\n+/g, "\n")
    .trim();
}

function extractArticle(html) {
  const title = decodeEntities(html.match(/<title>([\s\S]*?)\s*\|\s*Shopee Trung tâm trợ giúp<\/title>/i)?.[1] || "").trim();
  const content = html.match(/<div class="[^"]*ssr-key-content[^"]*">([\s\S]*?)<\/article>/i)?.[1]
    || html.match(/"content":"((?:\\.|[^"\\])*)"/i)?.[1]?.replace(/\\"/g, '"').replace(/\\n/g, "\n")
    || "";
  return { title, text: stripHtml(content) };
}

function classify(title) {
  const value = title.toLowerCase();
  if (/điều khoản|bảo mật|quyền riêng tư/.test(value)) return { category: "legal", type: "TERMS", authority: 100 };
  if (/trả hàng|hoàn tiền|hoàn xu/.test(value)) return { category: "refund", type: "POLICY", authority: 100 };
  if (/giao hàng|vận chuyển|nhận hàng/.test(value)) return { category: "shipping", type: "GUIDE", authority: 90 };
  if (/thanh toán|thẻ|ví|số dư/.test(value)) return { category: "payment", type: "GUIDE", authority: 90 };
  if (/voucher|mã giảm giá|khuyến mãi/.test(value)) return { category: "voucher", type: "FAQ", authority: 85 };
  if (/tài khoản|đăng nhập|mật khẩu|xác minh/.test(value)) return { category: "account", type: "GUIDE", authority: 90 };
  if (/hủy đơn|đơn hàng|đặt hàng/.test(value)) return { category: "orders", type: "FAQ", authority: 90 };
  return { category: "general", type: "FAQ", authority: 80 };
}

function isBuyerSupport(title) {
  return !/(người bán|kênh người bán|seller|quảng cáo|shopee ads|livestream|shopee video|spaylater|seasy|vay tiêu dùng|quick funds|test|testing)/i.test(title);
}

function chunks(text, maxLength = 3200) {
  const paragraphs = text.split("\n").map((item) => item.trim()).filter(Boolean);
  const result = [];
  let current = "";
  for (const paragraph of paragraphs) {
    if (current && current.length + paragraph.length + 1 > maxLength) {
      result.push(current);
      current = "";
    }
    current += `${current ? "\n" : ""}${paragraph}`;
  }
  if (current) result.push(current);
  return result;
}

async function fetchText(url) {
  const response = await fetch(url, { headers: {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "vi-VN,vi;q=0.9,en;q=0.7",
    "referer": "https://help.shopee.vn/portal/4",
  }, redirect: "follow" });
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return response.text();
}

async function mapLimit(values, limit, worker) {
  const output = new Array(values.length);
  let cursor = 0;
  await Promise.all(Array.from({ length: Math.min(limit, values.length) }, async () => {
    while (cursor < values.length) {
      const index = cursor++;
      output[index] = await worker(values[index], index);
    }
  }));
  return output;
}

async function main() {
  const sitemap = await fetchText(SITEMAP_URL);
  let urls = [...sitemap.matchAll(/<loc>(https:\/\/help\.shopee\.vn\/portal\/4\/article\/[^<]+)<\/loc>/g)]
    .map((match) => decodeEntities(match[1]))
    .map((url) => url.match(/\/article\/(\d+)/)?.[1])
    .filter(Boolean)
    .map((articleId) => `https://help.shopee.vn/portal/4/article/${articleId}?previousPage=other%20articles`);
  urls = [...new Set(urls)];
  if (MAX_PAGES > 0) urls = urls.slice(0, MAX_PAGES);
  const pages = (await mapLimit(urls, CONCURRENCY, async (url) => {
    try {
      const rawHtml = await fetchText(url);
      const article = extractArticle(rawHtml);
      if (!article.title || article.text.length < 80 || !isBuyerSupport(article.title)) return null;
      return { url, rawHtml, ...article, checksum: sha256(rawHtml) };
    } catch (error) {
      console.error(JSON.stringify({ url, error: String(error) }));
      return null;
    }
  })).filter(Boolean);
  if (!pages.length) throw new Error("Không lấy được bài viết Shopee nào; giữ nguyên KB hiện tại.");

  const source = await prisma.knowledgeSource.upsert({
    where: { baseUrl_locale: { baseUrl: "https://help.shopee.vn/portal/4", locale: "vi-VN" } },
    update: { authority: 100 },
    create: { name: "Shopee Việt Nam - Buyer Help Center", baseUrl: "https://help.shopee.vn/portal/4", locale: "vi-VN", authority: 100 },
  });
  const snapshotChecksum = sha256(pages.map((page) => `${page.url}:${page.checksum}`).sort().join("\n"));
  const existing = await prisma.knowledgeSourceSnapshot.findUnique({ where: { sourceId_checksum: { sourceId: source.id, checksum: snapshotChecksum } } });
  if (existing) return console.log(JSON.stringify({ snapshotId: existing.id, pages: existing.pageCount, unchanged: true }));

  await prisma.$transaction(async (tx) => {
    await tx.knowledgeDocument.deleteMany();
    const snapshot = await tx.knowledgeSourceSnapshot.create({ data: { sourceId: source.id, capturedAt: SNAPSHOT_DATE, sitemapUrl: SITEMAP_URL, checksum: snapshotChecksum, pageCount: pages.length, status: "RUNNING" } });
    for (const page of pages) {
      const articleId = page.url.match(/\/article\/(\d+)/)?.[1] || sha256(page.url).slice(0, 12);
      const classification = classify(page.title);
      const category = await tx.knowledgeCategory.upsert({ where: { slug: classification.category }, update: {}, create: { id: `shopee-${classification.category}`, slug: classification.category, name: classification.category } });
      const documentId = `shopee_${articleId}`;
      const versionId = `${documentId}_snapshot_20260729`;
      const document = await tx.knowledgeDocument.create({ data: { id: documentId, slug: `shopee-${articleId}`, locale: "vi-VN", type: classification.type, visibility: "PUBLIC", authorityLevel: classification.authority, categoryId: category.id, ownerId: "SHOPEE_VN" } });
      const version = await tx.knowledgeVersion.create({ data: { id: versionId, documentId: document.id, semanticVersion: "snapshot-2026.07.29", title: page.title, summary: page.text.slice(0, 320), content: page.text, status: "PUBLISHED", effectiveFrom: SNAPSHOT_DATE, searchable: true, changeSummary: "One-time official source snapshot", publishedAt: SNAPSHOT_DATE, publishedBy: "SYSTEM_CRAWLER" } });
      await tx.knowledgeDocument.update({ where: { id: document.id }, data: { currentVersionId: version.id } });
      const sourcePage = await tx.knowledgeSourcePage.create({ data: { snapshotId: snapshot.id, url: page.url, title: page.title, rawHtml: page.rawHtml, normalizedText: page.text, checksum: page.checksum, fetchedAt: new Date(), knowledgeDocumentId: document.id } });
      for (const [index, content] of chunks(page.text).entries()) {
        const chunk = await tx.knowledgeChunk.create({ data: { id: `${versionId}_chunk_${index + 1}`, versionId: version.id, section: index === 0 ? page.title : `${page.title} — phần ${index + 1}`, content, tokenCount: Math.ceil(content.length / 4) } });
        await tx.knowledgeSourceSection.create({ data: { sourcePageId: sourcePage.id, heading: chunk.section, content, ordinal: index, checksum: sha256(content), versionId: version.id, chunkId: chunk.id } });
      }
    }
    await tx.knowledgeSourceSnapshot.update({ where: { id: snapshot.id }, data: { status: "COMPLETED" } });
  }, { timeout: 600000 });
  console.log(JSON.stringify({ imported: pages.length, checksum: snapshotChecksum }));
}

main().catch((error) => { console.error(error); process.exitCode = 1; }).finally(() => prisma.$disconnect());
