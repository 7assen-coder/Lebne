import { NextResponse } from "next/server";
import { backendFetch } from "@/lib/backend";
import { getToken } from "@/lib/session";

export async function GET() {
  const token = await getToken();
  if (!token) return NextResponse.json({ user: null }, { status: 401 });
  const { res, data } = await backendFetch("/crowd/v1/auth/me", { token });
  if (!res.ok) return NextResponse.json({ user: null }, { status: 401 });
  return NextResponse.json(data);
}
