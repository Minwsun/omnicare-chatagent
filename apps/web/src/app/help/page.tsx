import Link from "next/link";

import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export default async function HelpPage() {
  const now = new Date();
  const documents = await prisma.knowledgeDocument.findMany({
    where: { visibility: "PUBLIC", archivedAt: null, currentVersion: { status: "PUBLISHED", searchable: true, effectiveFrom: { lte: now }, OR: [{ effectiveTo: null }, { effectiveTo: { gt: now } }] } },
    include: { currentVersion: true, category: true },
    orderBy: [{ authorityLevel: "desc" }, { updatedAt: "desc" }],
  });
  return <main className="shell help"><Link className="back-link" href="/">← OmniCare</Link><p className="eyebrow">KNOWLEDGE PLATFORM</p><h1>Trung tâm trợ giúp</h1><p>Chỉ hiển thị phiên bản public đang xuất bản và còn hiệu lực.</p><div className="data-list">{documents.map((document) => <Link className="data-card" key={document.id} href={`/help/${document.slug}`}><header><b>{document.currentVersion?.title}</b><span>{document.type}</span></header><p>{document.currentVersion?.summary}</p><small>{document.category.name} · v{document.currentVersion?.semanticVersion}</small></Link>)}</div></main>;
}
