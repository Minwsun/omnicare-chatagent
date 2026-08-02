import { NextResponse } from "next/server";

import { requireAdmin } from "@/lib/auth";
import { addTicketEvent } from "@/lib/handoff";
import { prisma } from "@/lib/prisma";

export async function POST(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const admin = await requireAdmin();
  if (!admin) return NextResponse.json({ error: "FORBIDDEN" }, { status: 403 });
  const { id } = await params;
  const claimed = await prisma.ticket.updateMany({ where: { id, assignedTo: null, status: { in: ["OPEN", "NEED_HUMAN", "PENDING_CUSTOMER", "PENDING_APPROVAL"] } }, data: { assignedTo: admin.id, status: "NEED_HUMAN" } });
  const ticket = await prisma.ticket.findUnique({ where: { id } });
  if (!ticket) return NextResponse.json({ error: "TICKET_NOT_FOUND" }, { status: 404 });
  if (!claimed.count && ticket.assignedTo !== admin.id) return NextResponse.json({ error: "ALREADY_ASSIGNED" }, { status: 409 });
  if (claimed.count) await addTicketEvent(id, "CLAIMED", { adminId: admin.id, email: admin.email });
  return NextResponse.json({ ticket: { ...ticket, assignedTo: ticket.assignedTo ?? admin.id } });
}
