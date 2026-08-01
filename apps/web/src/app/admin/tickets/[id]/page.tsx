import Link from "next/link";
import { notFound } from "next/navigation";

import { prisma } from "@/lib/prisma";

function json(value: unknown) { return JSON.stringify(value, null, 2); }

export default async function TicketDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ticket = await prisma.ticket.findUnique({ where: { id }, include: {
    customer: true,
    order: { include: { items: { include: { product: true } }, payments: true, shipments: { include: { events: { orderBy: { occurredAt: "asc" } } } }, refunds: true } },
    conversation: { include: { messages: { include: { attachments: true }, orderBy: { createdAt: "asc" } }, aiRuns: { orderBy: { startedAt: "desc" }, take: 20 } } },
    events: { orderBy: { createdAt: "desc" } },
  } });
  if (!ticket) notFound();

  return <><Link className="back-link" href="/admin/inbox">← Inbox</Link><p className="eyebrow">TICKET DETAIL</p><h1>{ticket.id}</h1><p>{ticket.summary}</p>
    <div className="fact-grid"><div><small>Trạng thái</small><b>{ticket.status}</b></div><div><small>Ưu tiên</small><b>{ticket.priority}</b></div><div><small>Phụ trách</small><b>{ticket.assignedTo ?? "Chưa phân công"}</b></div></div>
    <div className="admin-detail-grid"><section className="data-card"><h2>Khách hàng</h2><p><b>{ticket.customer?.name ?? "Khách vãng lai"}</b><br/>{ticket.customer?.email ?? "Không có email"}<br/>{ticket.customer?.phoneMasked ?? "Không có số điện thoại"}</p><small>{ticket.customer?.tier ?? "N/A"} · {ticket.customerId ?? "N/A"}</small></section><section className="data-card"><h2>Đơn hàng</h2>{ticket.order ? <><p><b>{ticket.order.id}</b> · {ticket.order.status}<br/>{Number(ticket.order.totalAmount).toLocaleString("vi-VN")} {ticket.order.currency}</p><small>{ticket.order.items.map((item)=>`${item.product.name} × ${item.quantity}`).join(", ")}</small></> : <p>Ticket không gắn đơn hàng.</p>}</section></div>
    <section className="admin-section"><h2>Hội thoại</h2><div className="timeline">{ticket.conversation.messages.map((message)=><article key={message.id}><header><b>{message.direction === "INBOUND" ? "Khách hàng" : "OmniCare"}</b><time>{message.createdAt.toLocaleString("vi-VN")}</time></header><p>{message.content}</p>{message.attachments.length > 0 && <small>{message.attachments.length} tệp đính kèm</small>}</article>)}</div></section>
    <section className="admin-section"><h2>AI runs liên quan</h2><div className="data-list compact">{ticket.conversation.aiRuns.map((run)=><Link className="data-card" href={`/admin/ai-runs/${run.id}`} key={run.id}><header><b>{run.intent ?? "UNCLASSIFIED"}</b><span>{run.completedAt ? (run.requiresHuman ? "HANDOFF" : "COMPLETED") : "RUNNING"}</span></header><small>{run.startedAt.toLocaleString("vi-VN")} · confidence {run.confidence?.toFixed(2) ?? "N/A"}</small></Link>)}</div></section>
    <section className="admin-section"><h2>Lịch sử ticket</h2><div className="timeline">{ticket.events.map((event)=><article key={event.id}><header><b>{event.type}</b><time>{event.createdAt.toLocaleString("vi-VN")}</time></header>{event.payload && <pre>{json(event.payload)}</pre>}</article>)}</div></section>
  </>;
}
