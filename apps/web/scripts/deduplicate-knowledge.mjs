import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

const groups = await prisma.$queryRaw`
  WITH active AS (
    SELECT d.id, v.id AS version_id,
           md5(lower(regexp_replace(v.content, '\s+', ' ', 'g'))) AS content_key
    FROM "KnowledgeDocument" d
    JOIN "KnowledgeVersion" v ON v.id = d."currentVersionId"
    WHERE d."archivedAt" IS NULL
  )
  SELECT content_key, array_agg(id ORDER BY id) AS document_ids
  FROM active
  GROUP BY content_key
  HAVING count(*) > 1
`;

let deleted = 0;
let migratedRetrievals = 0;

for (const group of groups) {
  const documents = await prisma.knowledgeDocument.findMany({
    where: { id: { in: group.document_ids } },
    include: { currentVersion: { include: { chunks: true } }, sourcePage: true },
  });
  documents.sort((left, right) =>
    Number(Boolean(right.sourcePage)) - Number(Boolean(left.sourcePage)) ||
    Number(right.id.startsWith("source_")) - Number(left.id.startsWith("source_")) ||
    right.authorityLevel - left.authorityLevel ||
    (right.currentVersion?.content.length ?? 0) - (left.currentVersion?.content.length ?? 0) ||
    right.updatedAt.getTime() - left.updatedAt.getTime(),
  );
  const canonical = documents[0];
  if (!canonical?.currentVersion) continue;
  const canonicalFallbackChunk = canonical.currentVersion.chunks.toSorted((left, right) => right.content.length - left.content.length)[0];
  if (!canonicalFallbackChunk) continue;

  for (const duplicate of documents.slice(1)) {
    if (!duplicate.currentVersion) continue;
    await prisma.$transaction(async (tx) => {
      const retrievals = await tx.aiRetrievalResult.findMany({ where: { versionId: duplicate.currentVersion.id }, include: { chunk: true } });
      for (const retrieval of retrievals) {
        const matchingChunk = canonical.currentVersion.chunks.find((chunk) => chunk.contentHash && chunk.contentHash === retrieval.chunk.contentHash) ?? canonicalFallbackChunk;
        await tx.aiRetrievalResult.update({ where: { id: retrieval.id }, data: { versionId: canonical.currentVersion.id, chunkId: matchingChunk.id } });
        migratedRetrievals += 1;
      }
      await tx.knowledgeFeedback.updateMany({ where: { documentId: duplicate.id }, data: { documentId: canonical.id, versionId: canonical.currentVersion.id } });
      await tx.graphDraftNode.updateMany({ where: { documentId: duplicate.id }, data: { documentId: canonical.id, versionId: canonical.currentVersion.id } });
      await tx.knowledgeSourcePage.updateMany({ where: { knowledgeDocumentId: duplicate.id }, data: { knowledgeDocumentId: null } });
      await tx.auditLog.create({ data: { actorId: "system", actorRole: "ADMIN", action: "KNOWLEDGE_DUPLICATE_MERGED_AND_DELETED", entityType: "KnowledgeDocument", entityId: duplicate.id, payload: { canonicalDocumentId: canonical.id, contentKey: group.content_key } } });
      await tx.knowledgeDocument.delete({ where: { id: duplicate.id } });
    }, { timeout: 30000 });
    deleted += 1;
  }
}

console.log(JSON.stringify({ groups: groups.length, deleted, migratedRetrievals }, null, 2));
await prisma.$disconnect();
