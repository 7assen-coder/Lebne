import { NextResponse } from "next/server";
import { z } from "zod";
import { backendFetch } from "@/lib/backend";
import { assertSameOrigin } from "@/lib/csrf";
import { clientError, proxyJson } from "@/lib/http";
import { setToken } from "@/lib/session";

const LoginSchema = z.object({
  email: z.string().trim().email().max(160),
  password: z.string().min(8).max(128),
});

export async function POST(req: Request) {
  const forbidden = assertSameOrigin(req);
  if (forbidden) return forbidden;

  const raw = await req.json().catch(() => null);
  const parsed = LoginSchema.safeParse(raw);
  if (!parsed.success) {
    return clientError(400, "Invalid email or password");
  }

  const { res, data } = await backendFetch("/crowd/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(parsed.data),
  });
  const payload = data as { access_token?: string; user?: unknown };
  if (!res.ok) {
    return proxyJson(res, null, "Login failed");
  }
  if (payload.access_token) await setToken(payload.access_token);
  return NextResponse.json({ ok: true, user: payload.user });
}
