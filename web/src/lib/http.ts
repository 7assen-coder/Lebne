import { NextResponse } from "next/server";

/** Stable client-facing errors — never forward raw backend/exception text. */
export function clientError(status: number, message: string) {
  return NextResponse.json({ error: message }, { status });
}

export function mapBackendStatus(status: number, fallback: string): string {
  if (status === 400) return "Invalid request";
  if (status === 401) return "Login required";
  if (status === 403) return "Forbidden";
  if (status === 404) return "Not found";
  if (status === 409) return "Conflict";
  if (status === 429) return "Too many requests";
  if (status >= 500) return fallback;
  return fallback;
}

export function proxyJson(
  res: { ok: boolean; status: number },
  data: unknown,
  fallback: string,
) {
  if (!res.ok) {
    const status = res.status >= 400 && res.status < 600 ? res.status : 502;
    return clientError(status, mapBackendStatus(status, fallback));
  }
  return NextResponse.json(data ?? { ok: true }, { status: res.status });
}
