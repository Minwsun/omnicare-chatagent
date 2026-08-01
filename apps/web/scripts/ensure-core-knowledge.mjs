import { createHash } from "node:crypto";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();
const normalize = (value) => value.normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase("vi");
const hash = (value) => createHash("sha256").update(normalize(value)).digest("hex");

const policies = [{
  id: "policy_privacy_core",
  slug: "chinh-sach-quyen-rieng-tu",
  categoryId: "legal",
  title: "Chính sách quyền riêng tư và bảo vệ dữ liệu cá nhân",
  summary: "Cách Omni thu thập, sử dụng, lưu trữ, bảo vệ và xử lý yêu cầu liên quan đến dữ liệu cá nhân.",
  content: "Omni chỉ thu thập thông tin cần thiết để tạo tài khoản, xử lý đơn hàng, thanh toán, giao nhận, phòng chống gian lận và hỗ trợ khách hàng. Dữ liệu có thể gồm thông tin liên hệ, địa chỉ nhận hàng, lịch sử giao dịch, lịch sử hỗ trợ và dữ liệu kỹ thuật phục vụ an toàn hệ thống. Omni giới hạn quyền truy cập theo nhiệm vụ, ghi nhận hoạt động truy cập và áp dụng biện pháp bảo vệ dữ liệu trong quá trình truyền và lưu trữ. Thông tin chỉ được lưu trong thời gian cần thiết cho mục đích đã thông báo, nghĩa vụ kế toán, giải quyết tranh chấp và yêu cầu pháp luật; hết thời hạn sẽ được xóa hoặc ẩn danh theo quy trình. Omni không yêu cầu khách hàng cung cấp mật khẩu hoặc mã OTP qua hội thoại hỗ trợ. Khách hàng có thể yêu cầu xem, cập nhật hoặc đề nghị xử lý dữ liệu của mình; các yêu cầu nhạy cảm phải được xác minh danh tính trước khi thực hiện. Dữ liệu giao dịch không được cung cấp cho tài khoản không sở hữu giao dịch đó.",
}];

for (const policy of policies) {
  const versionId = `${policy.id}_v_1_0_0`;
  const chunkId = `${versionId}_chunk_1`;
  await prisma.$transaction(async (tx) => {
    await tx.knowledgeDocument.upsert({
      where: { id: policy.id },
      update: { slug: policy.slug, type: "POLICY", visibility: "PUBLIC", marketplace: "SHOPEE", authorityLevel: 100, categoryId: policy.categoryId, archivedAt: null },
      create: { id: policy.id, slug: policy.slug, type: "POLICY", visibility: "PUBLIC", marketplace: "SHOPEE", authorityLevel: 100, categoryId: policy.categoryId, ownerId: "admin_demo" },
    });
    await tx.knowledgeVersion.upsert({
      where: { id: versionId },
      update: { title: policy.title, summary: policy.summary, content: policy.content, status: "PUBLISHED", searchable: true, effectiveTo: null },
      create: { id: versionId, documentId: policy.id, semanticVersion: "1.0.0", title: policy.title, summary: policy.summary, content: policy.content, status: "PUBLISHED", effectiveFrom: new Date("2026-01-01T00:00:00.000Z"), searchable: true, changeSummary: "Khởi tạo chính sách lõi", publishedAt: new Date(), publishedBy: "system" },
    });
    await tx.knowledgeChunk.upsert({
      where: { id: chunkId },
      update: { section: policy.title, content: policy.content, contentHash: hash(policy.content), retrievalEnabled: true, tokenCount: Math.ceil(policy.content.length / 4) },
      create: { id: chunkId, versionId, section: policy.title, content: policy.content, contentHash: hash(policy.content), retrievalEnabled: true, tokenCount: Math.ceil(policy.content.length / 4) },
    });
    await tx.knowledgeDocument.update({ where: { id: policy.id }, data: { currentVersionId: versionId } });
  });
}

console.log(JSON.stringify({ ensured: policies.map((policy) => policy.id) }));
await prisma.$disconnect();
