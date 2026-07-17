import { NextResponse } from "next/server";
import { assertSameOrigin } from "@/lib/csrf";
import { clearToken } from "@/lib/session";

export async function POST(req: Request) {
  const forbidden = assertSameOrigin(req);
  if (forbidden) return forbidden;
  await clearToken();
  return NextResponse.json({ ok: true });
}
