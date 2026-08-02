import { createHash, randomUUID } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();
const aiUrl = process.env.AI_SERVICE_URL || "http://localhost:8000";
const suffix = randomUUID().slice(0, 8);
const marker = `sao-lam-${suffix}`;
const question = `Theo chính sách, mã quy tắc ${marker} được xử lý thế nào?`;
const answerFact = `Mã quy tắc ${marker} cho phép khách hàng đổi lịch nhận hàng một lần trong vòng 37 phút kể từ khi xác nhận.`;
const ids = { document: `kb_lifecycle_${suffix}`, version: `kb_lifecycle_${suffix}_v1`, chunk: `kb_lifecycle_${suffix}_c1`, entity: `kb_lifecycle_${suffix}_e1`, claim: `kb_lifecycle_${suffix}_claim1` };

async function retrieve() {
  const response = await fetch(`${aiUrl}/retrieval/search`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ query: question, locale: "vi-VN", visibility: "CUSTOMER_AUTHENTICATED", limit: 10 }) });
  if (!response.ok) throw new Error(`Retrieval failed: ${response.status} ${await response.text()}`);
  return response.json();
}

async function clearCache() {
  let response = await fetch(`${aiUrl}/retrieval/cache/clear`, { method: "POST" });
  if (response.status === 404) response = await fetch(`${aiUrl}/retrieval/rebuild-all`, { method: "POST" });
  if (!response.ok) throw new Error(`Cache clear failed: ${response.status} ${await response.text()}`);
}

async function askAgent(stage) {
  const response = await fetch(`${aiUrl}/agent/run`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ message_id: `kb-${stage}-${suffix}`, content: question, customer_id: "customer_001", channel: "WEB", conversation_id: `kb-lifecycle-${stage}-${suffix}`, actor_role: "CUSTOMER", locale: "vi-VN" }) });
  if (!response.ok) throw new Error(`Agent failed: ${response.status} ${await response.text()}`);
  return response.json();
}

function snapshot(stage, retrieval, agent) {
  const normalizedAnswer = String(agent.answer || "").toLocaleLowerCase("vi-VN").normalize("NFD").replace(/\p{Diacritic}/gu, "");
  return {
    stage,
    retrievedCanary: retrieval.some((item) => item.document_id === ids.document),
    canaryRank: retrieval.findIndex((item) => item.document_id === ids.document) + 1 || null,
    retrieval: retrieval.map((item, index) => ({ rank: index + 1, documentId: item.document_id, title: item.title, score: item.score, scoreBreakdown: item.score_breakdown })),
    agent: { answer: agent.answer, mentionsCanaryFact: normalizedAnswer.includes("37 phut"), canaryCitation: agent.citations?.some((citation) => citation.document_id === ids.document) || false, citations: agent.citations || [], requiresHuman: agent.requires_human },
  };
}

async function createCanary() {
  const category = await prisma.knowledgeCategory.findFirst({ orderBy: { id: "asc" } });
  if (!category) throw new Error("Knowledge category required");
  const now = new Date();
  await prisma.$transaction(async (tx) => {
    await tx.knowledgeDocument.create({ data: { id: ids.document, slug: `kb-lifecycle-${suffix}`, locale: "vi-VN", type: "POLICY", visibility: "CUSTOMER_AUTHENTICATED", marketplace: "SHOPEE", authorityLevel: 99, categoryId: category.id, ownerId: "KB_LIFECYCLE_TEST" } });
    await tx.knowledgeVersion.create({ data: { id: ids.version, documentId: ids.document, semanticVersion: "1.0.0", title: `Chính sách kiểm thử ${marker}`, summary: answerFact, content: answerFact, status: "PUBLISHED", effectiveFrom: now, searchable: true, changeSummary: "KB lifecycle canary", publishedAt: now, publishedBy: "KB_LIFECYCLE_TEST" } });
    await tx.knowledgeChunk.create({ data: { id: ids.chunk, versionId: ids.version, section: marker, content: answerFact, contentHash: createHash("sha256").update(answerFact.toLocaleLowerCase("vi-VN").replace(/\s+/g, " ")).digest("hex"), retrievalEnabled: true, tokenCount: Math.ceil(answerFact.length / 4) } });
    await tx.knowledgeEntity.create({ data: { id: ids.entity, versionId: ids.version, chunkId: ids.chunk, type: "POLICY_RULE", canonicalName: marker, normalizedKey: marker, metadata: { testMarker: "KB_LIFECYCLE_TEST" } } });
    await tx.knowledgeClaim.create({ data: { id: ids.claim, versionId: ids.version, chunkId: ids.chunk, subject: marker, predicate: "allows_reschedule", value: answerFact, authorityLevel: 99, effectiveFrom: now, scope: { testMarker: "KB_LIFECYCLE_TEST" } } });
    await tx.knowledgeDocument.update({ where: { id: ids.document }, data: { currentVersionId: ids.version } });
  });
}

async function archiveCanary() {
  const now = new Date();
  await prisma.$transaction([
    prisma.knowledgeDocument.update({ where: { id: ids.document }, data: { archivedAt: now } }),
    prisma.knowledgeVersion.update({ where: { id: ids.version }, data: { searchable: false, effectiveTo: now } }),
    prisma.knowledgeChunk.update({ where: { id: ids.chunk }, data: { retrievalEnabled: false } }),
  ]);
}

async function restoreCanary() {
  await prisma.$transaction([
    prisma.knowledgeDocument.update({ where: { id: ids.document }, data: { archivedAt: null } }),
    prisma.knowledgeVersion.update({ where: { id: ids.version }, data: { searchable: true, effectiveTo: null } }),
    prisma.knowledgeChunk.update({ where: { id: ids.chunk }, data: { retrievalEnabled: true } }),
  ]);
}

async function cleanup() {
  const document = await prisma.knowledgeDocument.findUnique({ where: { id: ids.document } });
  if (!document) return;
  await prisma.knowledgeDocument.update({ where: { id: ids.document }, data: { currentVersionId: null } });
  await prisma.knowledgeDocument.delete({ where: { id: ids.document } });
}

const report = { marker, question, startedAt: new Date().toISOString(), stages: [], assertions: {} };
try {
  await cleanup();
  report.stages.push(snapshot("BEFORE_ADD", await retrieve(), await askAgent("before")));
  await createCanary();
  await clearCache();
  report.stages.push(snapshot("AFTER_ADD", await retrieve(), await askAgent("added")));
  await archiveCanary();
  await clearCache();
  report.stages.push(snapshot("AFTER_ARCHIVE", await retrieve(), await askAgent("archived")));
  await restoreCanary();
  await clearCache();
  report.stages.push(snapshot("AFTER_RESTORE", await retrieve(), await askAgent("restored")));
  report.assertions = {
    retrievalAbsentBefore: !report.stages[0].retrievedCanary,
    answerAbsentBefore: !report.stages[0].agent.mentionsCanaryFact,
    citationAbsentBefore: !report.stages[0].agent.canaryCitation,
    retrievalPresentAfterAdd: report.stages[1].retrievedCanary,
    answerGroundedAfterAdd: report.stages[1].agent.mentionsCanaryFact,
    citationCorrectAfterAdd: report.stages[1].agent.canaryCitation,
    rankedAfterAdd: report.stages[1].canaryRank !== null && report.stages[1].canaryRank <= 3,
    retrievalAbsentAfterArchive: !report.stages[2].retrievedCanary,
    answerAbsentAfterArchive: !report.stages[2].agent.mentionsCanaryFact,
    citationAbsentAfterArchive: !report.stages[2].agent.canaryCitation,
    retrievalPresentAfterRestore: report.stages[3].retrievedCanary,
    answerGroundedAfterRestore: report.stages[3].agent.mentionsCanaryFact,
    citationCorrectAfterRestore: report.stages[3].agent.canaryCitation,
    rankedAfterRestore: report.stages[3].canaryRank !== null && report.stages[3].canaryRank <= 3,
  };
  if (Object.values(report.assertions).some((value) => !value)) throw new Error(`Lifecycle assertion failed: ${JSON.stringify(report.assertions)}`);
} finally {
  await cleanup();
  report.cleanedUp = !(await prisma.knowledgeDocument.findUnique({ where: { id: ids.document } }));
  report.completedAt = new Date().toISOString();
  await mkdir("../../datasets/artifacts", { recursive: true });
  await writeFile("../../datasets/artifacts/kb-lifecycle-report.json", JSON.stringify(report, null, 2));
  await prisma.$disconnect();
}

console.log(JSON.stringify({ marker: report.marker, assertions: report.assertions, cleanedUp: report.cleanedUp }, null, 2));
