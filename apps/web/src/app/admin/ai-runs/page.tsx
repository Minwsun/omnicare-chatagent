import Link from "next/link";
import { Prisma } from "@prisma/client";

import { prisma } from "@/lib/prisma";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function AiRunsPage({ searchParams }: { searchParams: SearchParams }) {
  const query = await searchParams;
  const search = typeof query.search === "string" ? query.search.trim() : "";
  const handoff = query.handoff === "true";
  const where: Prisma.AiRunWhereInput = { ...(handoff ? { requiresHuman: true } : {}), ...(search ? { OR: [{ id: { contains: search, mode: "insensitive" } }, { conversationId: { contains: search, mode: "insensitive" } }, { intent: { contains: search, mode: "insensitive" } }] } : {}) };
  const runs = await prisma.aiRun.findMany({ where, include: { _count: { select: { steps: true, toolCalls: true, retrievals: true } } }, orderBy: { startedAt: "desc" }, take: 100 });
  return <><p className="eyebrow">AGENT OBSERVABILITY</p><h1>AI Runs</h1><form className="admin-filters"><input name="search" defaultValue={search} placeholder="Run, conversation, intent…"/><label className="checkbox-filter"><input type="checkbox" name="handoff" value="true" defaultChecked={handoff}/> Chỉ handoff</label><button>Tìm</button></form><div className="data-list">{runs.map((run) => { const latency = run.completedAt ? run.completedAt.getTime()-run.startedAt.getTime() : null; return <Link className="data-card" href={`/admin/ai-runs/${run.id}`} key={run.id}><header><b>{run.intent ?? "UNCLASSIFIED"}</b><span>{run.completedAt ? (run.requiresHuman ? "HANDOFF" : "COMPLETED") : "RUNNING"}</span></header><p>{run.id}</p><small>{run._count.steps} steps · {run._count.toolCalls} tools · {run._count.retrievals} evidence · {latency === null ? "đang chạy" : `${latency} ms`}</small></Link>})}</div>{!runs.length && <p className="empty-state">Không tìm thấy AI run phù hợp.</p>}</>;
}
