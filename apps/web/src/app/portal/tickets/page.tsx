import { requireCustomer } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export default async function TicketsPage() {
  const user = await requireCustomer();
  const tickets = await prisma.ticket.findMany({ where: { customerId: user!.customerId! }, orderBy: { updatedAt: "desc" } });
  return <section className="shell"><p className="eyebrow">SUPPORT TICKETS</p><h1>Yêu cầu hỗ trợ</h1><div className="data-list">{tickets.map((ticket) => <article className="data-card" key={ticket.id}><header><b>{ticket.id}</b><span>{ticket.status}</span></header><p>{ticket.summary}</p><small>{ticket.priority} · {ticket.category}</small></article>)}</div></section>;
}
