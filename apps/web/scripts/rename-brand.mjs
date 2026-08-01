import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();
const replace = (column) => `replace(replace(replace(replace(replace(replace(replace(${column}, 'ShopeeVIP', 'OmniVIP'), 'Shopee VIP', 'OmniVIP'), 'SPayLater', 'OmniPayLater'), 'ShopeeFood', 'OmniFood'), 'SHOPEE', 'OMNI'), 'shopee', 'omni'), 'Shopee', 'Omni')`;

try {
  const statements = [
    `UPDATE "KnowledgeVersion" SET title=${replace("title")}, summary=${replace("summary")}, content=${replace("content")}, "changeSummary"=${replace('COALESCE("changeSummary", \'\')')}`,
    `UPDATE "KnowledgeChunk" SET section=${replace("section")}, content=${replace("content")}`,
    `UPDATE "KnowledgeEntity" SET "canonicalName"=${replace('"canonicalName"')}`,
    `UPDATE "KnowledgeClaim" SET subject=${replace("subject")}, predicate=${replace("predicate")}, value=${replace("value")}`,
    `UPDATE "KnowledgeCategory" SET name=${replace("name")}`,
    `UPDATE "Message" SET content=${replace("content")}, metadata=CASE WHEN metadata IS NULL THEN NULL ELSE (${replace("metadata::text")})::jsonb END`,
  ];
  for (const statement of statements) await prisma.$executeRawUnsafe(statement);
  console.log(JSON.stringify({ renamed: true, preserved: ["sourceUrl", "documentId", "sourceType"] }));
} finally {
  await prisma.$disconnect();
}
