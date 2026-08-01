import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();
const SNAPSHOT_ID = process.env.KB_SNAPSHOT_ID || "marketplace-policy-2026-07-30";
const SNAPSHOT_DATE = new Date("2026-07-30T00:00:00.000Z");
const MAX_PAGES = Number(process.env.KB_MAX_PAGES || 0);
const CONCURRENCY = Math.max(1, Math.min(3, Number(process.env.KB_CRAWL_CONCURRENCY || 2)));
const MANIFEST_PATH = resolve(process.env.KB_MANIFEST_PATH || "scripts/artifacts/marketplace-policy-2026-07-30.json");
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const sleep = (milliseconds) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));

const TIKTOK_SEEDS = [
  "https://seller-vn.tiktok.com/university/essay?knowledge_id=6837773789234946&lang=en",
  "https://seller-vn.tiktok.com/university/essay?knowledge_id=1766935302801169&lang=en",
  "https://seller-vn.tiktok.com/university/essay?knowledge_id=2901402355762946&lang=en",
  "https://seller-vn.tiktok.com/university/essay?knowledge_id=7045464018339600&lang=en",
  "https://seller-vn.tiktok.com/university/essay?knowledge_id=7179954358388497&lang=en",
  "https://seller-vn.tiktok.com/university/essay?knowledge_id=6837773789169410&lang=en",
  "https://seller-vn.tiktok.com/university/essay?knowledge_id=8831988245645057&lang=en",
];

function decodeEntities(value) {
  return value.replace(/&nbsp;|&#160;/gi," ").replace(/&amp;/gi,"&").replace(/&lt;/gi,"<").replace(/&gt;/gi,">").replace(/&quot;/gi,'"').replace(/&#39;|&apos;/gi,"'").replace(/&#(\d+);/g,(_,code)=>String.fromCodePoint(Number(code)));
}

function stripHtml(html) {
  return decodeEntities(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi," ").replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi," ").replace(/<\/(p|li|h[1-6]|tr|div|section|article)>/gi,"\n").replace(/<br\s*\/?>/gi,"\n").replace(/<[^>]+>/g," ")).replace(/\r/g,"").replace(/[ \t]+/g," ").replace(/\n\s*\n+/g,"\n").trim();
}

function extractPage(marketplace, html, url) {
  const jsonTitle = html.match(/"title":"((?:\\.|[^"\\])*)"/i)?.[1];
  const rawTitle = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] || html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i)?.[1] || (jsonTitle ? JSON.parse(`"${jsonTitle}"`) : url);
  const title = stripHtml(rawTitle).replace(/\s*[|–-]\s*(Shopee|TikTok Shop).*$/i,"").trim();
  const jsonContent = html.match(/"content":"((?:\\.|[^"\\])*)"/i)?.[1];
  const decodedJsonContent = jsonContent ? JSON.parse(`"${jsonContent}"`) : "";
  const article = html.match(/<div class="[^"]*ssr-key-content[^"]*">([\s\S]*?)<\/div>/i)?.[1] || html.match(/<article\b[^>]*>([\s\S]*?)<\/article>/i)?.[1] || html.match(/<main\b[^>]*>([\s\S]*?)<\/main>/i)?.[1] || decodedJsonContent || html;
  const text = stripHtml(article);
  return { marketplace, url, title, text, rawHtml: html, checksum: sha256(`${title}\n${text}`) };
}

function classify(title, text) {
  const value = `${title} ${text.slice(0,1200)}`.toLocaleLowerCase("vi-VN");
  if (/điều khoản|terms|privacy|bảo mật|quyền riêng tư/.test(value)) return ["legal","TERMS",100];
  if (/trả hàng|return|hoàn tiền|refund|aftersale/.test(value)) return ["refund","POLICY",100];
  if (/hủy đơn|cancellation|đặt hàng|order/.test(value)) return ["orders","POLICY",95];
  if (/giao hàng|shipping|delivery|vận chuyển/.test(value)) return ["shipping","GUIDE",90];
  if (/thanh toán|payment|cod|wallet/.test(value)) return ["payment","GUIDE",90];
  if (/sản phẩm bị cấm|prohibited|restricted product/.test(value)) return ["warranty","POLICY",95];
  if (/voucher|khuyến mãi|promotion/.test(value)) return ["voucher","FAQ",85];
  if (/tài khoản|account|login|password/.test(value)) return ["account","GUIDE",90];
  return ["orders","FAQ",80];
}

function chunks(text, maxLength=3000) {
  const paragraphs=text.split("\n").map((item)=>item.trim()).filter((item)=>item.length>20); const output=[]; let current="";
  for(const paragraph of paragraphs){if(current&&current.length+paragraph.length+1>maxLength){output.push(current);current="";}current+=`${current?"\n":""}${paragraph}`;} if(current)output.push(current); return output;
}

async function fetchText(url) {
  const response=await fetch(url,{headers:{"user-agent":"OmniCarePolicySnapshot/1.0 (+internal-research; snapshot 2026-07-30)","accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","accept-language":"vi-VN,vi;q=0.9,en;q=0.7"},redirect:"follow"});
  if(!response.ok)throw new Error(`${response.status} ${url}`); return response.text();
}

async function discoverShopee() {
  const sitemapUrl="https://help.shopee.vn/sitemap.xml"; const xml=await fetchText(sitemapUrl);
  const urls=[...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match)=>decodeEntities(match[1])).filter((url)=>/help\.shopee\.vn\/portal\/4\/article\//.test(url));
  return { sitemapUrl, urls:[...new Set(urls.map((url)=>url.match(/\/article\/(\d+)/)?.[1]).filter(Boolean).map((articleId)=>`https://help.shopee.vn/portal/4/article/${articleId}?previousPage=other%20articles`))] };
}

async function discoverTikTok() {
  const discovered=new Set(TIKTOK_SEEDS);
  for(const seed of TIKTOK_SEEDS.slice(0,2)){try{const html=await fetchText(seed); for(const match of html.matchAll(/https:\/\/seller-vn\.tiktok\.com\/university\/essay\?[^"'< ]*knowledge_id=\d+[^"'< ]*/g))discovered.add(decodeEntities(match[0]));}catch{}}
  return { sitemapUrl:"seed-list://tiktok-shop-vietnam", urls:[...discovered] };
}

async function mapLimit(values, worker) {
  const output=[]; let cursor=0;
  await Promise.all(Array.from({length:Math.min(CONCURRENCY,values.length)},async()=>{while(cursor<values.length){const index=cursor++; output[index]=await worker(values[index],index); await sleep(500);}})); return output;
}

async function crawlAdapter(marketplace, discovery) {
  let urls=discovery.urls; if(MAX_PAGES>0)urls=urls.slice(0,MAX_PAGES); const failures=[];
  const pages=(await mapLimit(urls,async(url)=>{try{const html=await fetchText(url);const page=extractPage(marketplace,html,url);if(!page.title||page.text.length<120)throw new Error("CONTENT_TOO_SHORT");return page;}catch(error){failures.push({url,error:String(error)});return null;}})).filter(Boolean);
  return { marketplace, sitemapUrl:discovery.sitemapUrl, requested:urls.length, pages, failures };
}

async function importSnapshot(adapter) {
  if (!adapter.pages.length) return { snapshotId:null, unchanged:false, imported:0, skipped:"NO_VALID_PAGES" };
  const baseUrl=adapter.marketplace==="SHOPEE"?"https://help.shopee.vn/portal/4":"https://seller-vn.tiktok.com/university";
  const source=await prisma.knowledgeSource.upsert({where:{baseUrl_locale:{baseUrl,locale:"vi-VN"}},update:{authority:100},create:{name:`${adapter.marketplace} official policy snapshot`,baseUrl,locale:"vi-VN",authority:100}});
  const checksum=sha256(adapter.pages.map((page)=>`${page.url}:${page.checksum}`).sort().join("\n"));
  const existing=await prisma.knowledgeSourceSnapshot.findUnique({where:{sourceId_checksum:{sourceId:source.id,checksum}}}); if(existing)return {snapshotId:existing.id,unchanged:true,imported:existing.pageCount};
  const snapshot=await prisma.knowledgeSourceSnapshot.create({data:{sourceId:source.id,capturedAt:SNAPSHOT_DATE,sitemapUrl:adapter.sitemapUrl,checksum,pageCount:adapter.pages.length,status:"RUNNING"}});
  for(const page of adapter.pages){
    const key=sha256(page.url).slice(0,16); const [categorySlug,type,authority]=classify(page.title,page.text); const category=await prisma.knowledgeCategory.upsert({where:{slug:categorySlug},update:{},create:{id:`marketplace-${categorySlug}`,slug:categorySlug,name:categorySlug}});
    const sourceDocumentId=`source_${adapter.marketplace.toLowerCase()}_${key}`; const sourceVersionId=`${sourceDocumentId}_${SNAPSHOT_ID}`; const sourceSlug=`source-${adapter.marketplace.toLowerCase()}-${key}`;
    if (await prisma.knowledgeVersion.findUnique({ where: { id: sourceVersionId } })) continue;
    const document=await prisma.knowledgeDocument.upsert({where:{id:sourceDocumentId},update:{authorityLevel:authority,archivedAt:null},create:{id:sourceDocumentId,slug:sourceSlug,locale:"vi-VN",type,visibility:"CUSTOMER_AUTHENTICATED",authorityLevel:authority,categoryId:category.id,ownerId:`${adapter.marketplace}_SNAPSHOT`}});
    const version=await prisma.knowledgeVersion.create({data:{id:sourceVersionId,documentId:document.id,semanticVersion:SNAPSHOT_ID,title:`[Nguồn ${adapter.marketplace}] ${page.title}`,summary:page.text.slice(0,320),content:page.text,status:"PUBLISHED",effectiveFrom:SNAPSHOT_DATE,searchable:true,changeSummary:`Official source snapshot ${SNAPSHOT_ID}`,publishedAt:SNAPSHOT_DATE,publishedBy:"SYSTEM_CRAWLER"}});
    await prisma.knowledgeDocument.update({where:{id:document.id},data:{currentVersionId:version.id}});
    const sourcePage=await prisma.knowledgeSourcePage.create({data:{snapshotId:snapshot.id,url:page.url,title:page.title,rawHtml:page.rawHtml,normalizedText:page.text,checksum:page.checksum,fetchedAt:new Date(),knowledgeDocumentId:document.id}});
    for(const [index,content] of chunks(page.text).entries()){const chunk=await prisma.knowledgeChunk.create({data:{id:`${sourceVersionId}_chunk_${index+1}`,versionId:version.id,section:index===0?page.title:`${page.title} — phần ${index+1}`,content,tokenCount:Math.max(1,Math.ceil(content.length/4))}});await prisma.knowledgeSourceSection.create({data:{sourcePageId:sourcePage.id,heading:chunk.section,content,ordinal:index,checksum:sha256(content),versionId:version.id,chunkId:chunk.id}});}
    const draftId=`omnicare_draft_${adapter.marketplace.toLowerCase()}_${key}`;
    await prisma.knowledgeDocument.upsert({where:{id:draftId},update:{},create:{id:draftId,slug:`omnicare-draft-${adapter.marketplace.toLowerCase()}-${key}`,locale:"vi-VN",type,visibility:"INTERNAL",authorityLevel:70,categoryId:category.id,ownerId:"OMNICARE_POLICY_TEAM",versions:{create:{id:`${draftId}_v1`,semanticVersion:"0.1.0",title:`OmniCare draft — ${page.title}`,summary:`Bản nháp tham khảo từ ${adapter.marketplace}. Cần admin duyệt trước publish.`,content:`Nguồn tham khảo: ${page.url}\nChecksum: ${page.checksum}\n\n${page.text}`,status:"DRAFT",effectiveFrom:SNAPSHOT_DATE,searchable:false,changeSummary:`Derived from ${adapter.marketplace} snapshot; not approved`}}}});
  }
  await prisma.knowledgeSourceSnapshot.update({where:{id:snapshot.id},data:{status:"COMPLETED"}}); return {snapshotId:snapshot.id,unchanged:false,imported:adapter.pages.length};
}

async function main(){
  const discovered=await Promise.all([discoverShopee(),discoverTikTok()]); const adapters=await Promise.all([crawlAdapter("SHOPEE",discovered[0]),crawlAdapter("TIKTOK_SHOP",discovered[1])]); const imports=[];
  for(const adapter of adapters)imports.push({marketplace:adapter.marketplace,...await importSnapshot(adapter)});
  const manifest={snapshotId:SNAPSHOT_ID,capturedAt:SNAPSHOT_DATE.toISOString(),adapters:adapters.map((item)=>({marketplace:item.marketplace,sitemapUrl:item.sitemapUrl,requested:item.requested,succeeded:item.pages.length,failed:item.failures.length,failures:item.failures})),imports}; await mkdir(dirname(MANIFEST_PATH),{recursive:true});await writeFile(MANIFEST_PATH,`${JSON.stringify(manifest,null,2)}\n`,"utf8"); console.log(JSON.stringify(manifest));
}

main().catch((error)=>{console.error(error);process.exitCode=1;}).finally(()=>prisma.$disconnect());
