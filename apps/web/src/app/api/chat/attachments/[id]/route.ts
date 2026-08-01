import { NextResponse } from "next/server";

import { requireCustomer } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await requireCustomer();
  if (!user?.customerId) return NextResponse.json({ error: "AUTHENTICATION_REQUIRED" }, { status: 401 });
  const { id } = await params;
  const attachment = await prisma.chatAttachment.findFirst({ where: { id, customerId: user.customerId, deletedAt: null }, select: { bytes: true, mimeType: true, fileName: true } });
  if (!attachment?.bytes) return NextResponse.json({ error: "ATTACHMENT_NOT_FOUND" }, { status: 404 });
  return new Response(attachment.bytes, { headers: { "content-type": attachment.mimeType, "content-disposition": `inline; filename="${attachment.fileName.replaceAll('"', '')}"`, "cache-control": "private, max-age=300" } });
}
