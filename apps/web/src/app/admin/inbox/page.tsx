import Link from "next/link";
import { Prisma } from "@prisma/client";

import { prisma } from "@/lib/prisma";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function InboxPage({ searchParams }: { searchParams: SearchParams }) {
  const query = await searchParams;
  const search = typeof query.search === "string" ? query.search.trim() : "";
  const status = typeof query.status === "string" ? query.status : "";
  const priority = typeof query.priority === "string" ? query.priority : "";
  const where: Prisma.TicketWhereInput = {
    ...(status ? { status: status as Prisma.EnumTicketStatusFilter } : {}),
    ...(priority ? { priority: priority as Prisma.EnumPriorityFilter } : {}),
    ...(search ? { OR: [
      { id: { contains: search, mode: "insensitive" } },
      { summary: { contains: search, mode: "insensitive" } },
      { category: { contains: search, mode: "insensitive" } },
      { customer: { is: { OR: [{ name: { contains: search, mode: "insensitive" } }, { email: { contains: search, mode: "insensitive" } }] } } },
      { orderId: { contains: search, mode: "insensitive" } },
    ] } : {}),
  };
  const tickets = await prisma.ticket.findMany({ where, include: { customer: true, order: true, conversation: { select: { _count: { select: { messages: true } } } }, _count: { select: { events: true } } }, orderBy: [{ updatedAt: "desc" }], take: 100 });

  return <><p className="eyebrow">HUMAN QUEUE</p><div className="admin-title"><div><h1>Yêu cầu hỗ trợ</h1><p>{tickets.length} ticket gần nhất, mới cập nhật trước.</p></div></div>
    <form className="admin-filters"><input name="search" defaultValue={search} placeholder="Ticket, khách hàng, email, đơn hàng…"/><select name="status" defaultValue={status}><option value="">Mọi trạng thái</option>{["OPEN","NEED_HUMAN","PENDING_CUSTOMER","PENDING_APPROVAL","RESOLVED","CLOSED"].map((value)=><option key={value}>{value}</option>)}</select><select name="priority" defaultValue={priority}><option value="">Mọi ưu tiên</option>{["URGENT","HIGH","MEDIUM","LOW"].map((value)=><option key={value}>{value}</option>)}</select><button>Tìm</button></form>
    <div className="data-list">{tickets.map((ticket) => <Link className="data-card" href={`/admin/tickets/${ticket.id}`} key={ticket.id}><header><b>{ticket.id} · {ticket.customer?.name ?? "Khách vãng lai"}</b><span>{ticket.status}</span></header><p>{ticket.summary}</p><small>{ticket.priority} · {ticket.category} · {ticket.orderId ?? "Không gắn đơn"} · {ticket.conversation._count.messages} tin nhắn · {ticket._count.events} sự kiện</small></Link>)}</div>
    {!tickets.length && <p className="empty-state">Không tìm thấy ticket phù hợp.</p>}
  </>;
}
