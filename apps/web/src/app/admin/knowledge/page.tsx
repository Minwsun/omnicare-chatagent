import { prisma } from "@/lib/prisma";
import KnowledgeManager from "./knowledge-manager";

export default async function KnowledgePage() {
  const [documents, runs] = await Promise.all([
    prisma.knowledgeDocument.findMany({ where: { archivedAt: null }, include: { currentVersion: true, category: true }, orderBy: [{ authorityLevel: "desc" }, { updatedAt: "desc" }], take: 300 }),
    prisma.knowledgeIngestionRun.findMany({ where: { documentId: { not: null } }, orderBy: { createdAt: "desc" }, take: 1000 }),
  ]);
  const latestRunByDocument = new Map<string, typeof runs[number]>();
  for (const run of runs) if (run.documentId && !latestRunByDocument.has(run.documentId)) latestRunByDocument.set(run.documentId, run);
  return <><p className="eyebrow">KNOWLEDGE MANAGEMENT</p><KnowledgeManager initialDocuments={documents.map((document) => {
    const run = latestRunByDocument.get(document.id);
    return { id: document.id, type: document.type, visibility: document.visibility, authorityLevel: document.authorityLevel, archived: Boolean(document.archivedAt), title: document.currentVersion?.title || "Chưa có phiên bản", summary: document.currentVersion?.summary || "", content: document.currentVersion?.content || "", priority: run?.priority || "NORMAL", pipelineStatus: run?.status || "DONE", pipelineStage: run?.stage || null, pipelineProgress: run?.progress || 0, latestRunId: run?.id || null };
  })} /></>;
}
