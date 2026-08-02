import { NextResponse } from "next/server";

import { requireAdmin } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function POST(_: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!await requireAdmin()) return NextResponse.json({ error: "FORBIDDEN" }, { status: 403 });
  const { id } = await params;
  const ticket = await prisma.ticket.findUnique({ where: { id }, include: { customer: true, order: true, events: { orderBy: { createdAt: "desc" }, take: 5 }, conversation: { include: { messages: { orderBy: { createdAt: "desc" }, take: 12 } } } } });
  if (!ticket) return NextResponse.json({ error: "TICKET_NOT_FOUND" }, { status: 404 });
  const recent = ticket.conversation.messages.slice().reverse().map((message) => `${message.direction}: ${message.content}`).join("\n");
  const serviceUrl = process.env.AI_SERVICE_URL;
  if (!serviceUrl) return NextResponse.json({ error: "AI_SERVICE_NOT_CONFIGURED" }, { status: 503 });
  const response = await fetch(`${serviceUrl}/admin/assist`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ ticket_id: ticket.id, category: ticket.category, priority: ticket.priority, summary: ticket.summary, customer: ticket.customer, order: ticket.order, conversation: recent }), cache: "no-store" });
  if (!response.ok) return NextResponse.json({ error: "AI_ASSIST_UNAVAILABLE" }, { status: 503 });
  return NextResponse.json(await response.json());
}
