import { NextResponse } from "next/server";

function allowedHosts(): Set<string> {
  const hosts = new Set<string>();
  for (const raw of [
    process.env.APP_URL,
    process.env.NEXT_PUBLIC_APP_URL,
    process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : null,
    process.env.VERCEL_PROJECT_PRODUCTION_URL
      ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
      : null,
  ]) {
    if (!raw) continue;
    try {
      hosts.add(new URL(raw.includes("://") ? raw : `https://${raw}`).host);
    } catch {
      /* ignore bad env */
    }
  }
  if (process.env.NODE_ENV !== "production") {
    hosts.add("localhost:3000");
    hosts.add("127.0.0.1:3000");
  }
  return hosts;
}

/** Reject cross-site mutating requests that still carry the session cookie. */
export function assertSameOrigin(req: Request): NextResponse | null {
  const site = (req.headers.get("sec-fetch-site") || "").toLowerCase();
  if (site === "cross-site") {
    return NextResponse.json({ error: "Forbidden origin" }, { status: 403 });
  }

  const origin = req.headers.get("origin");
  if (!origin) {
    // Prefer Sec-Fetch-Site when Origin is absent (some same-origin cases).
    if (site === "same-origin" || site === "same-site" || site === "none" || !site) {
      return null;
    }
    return NextResponse.json({ error: "Forbidden origin" }, { status: 403 });
  }

  try {
    const o = new URL(origin);
    const allow = allowedHosts();
    // Prefer allowlist; Host header only as secondary check (not X-Forwarded-Host alone).
    if (allow.size > 0 && allow.has(o.host)) return null;
    const host = req.headers.get("host");
    if (host && o.host === host && (site === "same-origin" || site === "same-site" || !site)) {
      return null;
    }
  } catch {
    /* fall through */
  }
  return NextResponse.json({ error: "Forbidden origin" }, { status: 403 });
}
