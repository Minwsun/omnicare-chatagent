import { createHash } from "node:crypto";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();
const dryRun = process.argv.includes("--dry-run");
const normalize = (value) => value.normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase("vi");
const hash = (value) => createHash("sha256").update(normalize(value)).digest("hex");

const documents = await prisma.knowledgeDocument.findMany({
  where: { archivedAt: null, currentVersionId: { not: null } },
  include: { currentVersion: { include: { chunks: true } }, sourcePage: true },
});

const groups = new Map();
for (const document of documents) {
  if (!document.currentVersion) continue;
  const key = [document.type, document.locale, normalize(document.currentVersion.title)].join("|");
  groups.set(key, [...(groups.get(key) ?? []), document]);
}

let archived = 0;
let backfilledChunks = 0;
for (const group of groups.values()) {
  group.sort((left, right) =>
    Number(Boolean(right.sourcePage)) - Number(Boolean(left.sourcePage)) ||
    right.authorityLevel - left.authorityLevel ||
    (right.currentVersion?.content.length ?? 0) - (left.currentVersion?.content.length ?? 0) ||
    right.updatedAt.getTime() - left.updatedAt.getTime(),
  );
  const canonical = group[0];
  if (!canonical?.currentVersion) continue;

  for (const document of group) {
    for (const chunk of document.currentVersion?.chunks ?? []) {
      const contentHash = hash(chunk.content);
      if (chunk.contentHash === contentHash) continue;
      backfilledChunks += 1;
      if (!dryRun) await prisma.knowledgeChunk.update({ where: { id: chunk.id }, data: { contentHash } });
    }
  }

  for (const duplicate of group.slice(1)) {
    if (!duplicate.currentVersion) continue;
    archived += 1;
    if (dryRun) continue;
    await prisma.$transaction(async (tx) => {
      await tx.knowledgeChunk.updateMany({ where: { versionId: duplicate.currentVersion.id }, data: { retrievalEnabled: false } });
      await tx.knowledgeVersion.update({ where: { id: duplicate.currentVersion.id }, data: { searchable: false, status: "ARCHIVED" } });
      await tx.knowledgeDocument.update({ where: { id: duplicate.id }, data: { archivedAt: new Date() } });
      await tx.auditLog.create({
        data: {
          actorId: "system",
          actorRole: "ADMIN",
          action: "KNOWLEDGE_DUPLICATE_ARCHIVED",
          entityType: "KnowledgeDocument",
          entityId: duplicate.id,
          payload: { canonicalDocumentId: canonical.id, normalizedTitle: normalize(duplicate.currentVersion.title) },
        },
      });
    }, { timeout: 30000 });
  }
}

console.log(JSON.stringify({ dryRun, activeDocuments: documents.length, duplicateGroups: [...groups.values()].filter((group) => group.length > 1).length, archived, backfilledChunks }, null, 2));
await prisma.$disconnect();
