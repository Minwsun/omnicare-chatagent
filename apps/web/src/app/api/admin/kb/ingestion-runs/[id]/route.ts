import { NextResponse } from "next/server";
import { requireAdmin } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!await requireAdmin()) return NextResponse.json({ error: "FORBIDDEN" }, { status: 403 });
  const { id } = await params;
  const run = await prisma.knowledgeIngestionRun.findUnique({ where: { id } });
  return run ? NextResponse.json(run) : NextResponse.json({ error: "RUN_NOT_FOUND" }, { status: 404 });
}
