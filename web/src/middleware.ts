import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const COOKIE = "lebne_crowd_token";
const ACTIVE_COOKIE = "lebne_crowd_active";
const IDLE_SECONDS = Number(process.env.LEBNE_CROWD_IDLE_SECONDS || 600);
const MAX_AGE_SECONDS = Number(process.env.LEBNE_CROWD_TOKEN_TTL_HOURS || 12) * 60 * 60;

function clearSession(res: NextResponse) {
  res.cookies.set(COOKIE, "", { httpOnly: true, sameSite: "lax", path: "/", maxAge: 0 });
  res.cookies.set(ACTIVE_COOKIE, "", { httpOnly: true, sameSite: "lax", path: "/", maxAge: 0 });
  return res;
}

function isIdleExpired(activeRaw: string | undefined) {
  if (!activeRaw) return true;
  const ts = Number(activeRaw);
  if (!Number.isFinite(ts)) return true;
  return Math.floor(Date.now() / 1000) - ts > IDLE_SECONDS;
}

/** Early gate — pages still re-check role via getSession(). */
export function middleware(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value;
  const { pathname } = req.nextUrl;

  if (!token) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json({ error: "Login required" }, { status: 401 });
    }
    const login = req.nextUrl.clone();
    login.pathname = "/login";
    login.search = "";
    return NextResponse.redirect(login);
  }

  const active = req.cookies.get(ACTIVE_COOKIE)?.value;
  if (isIdleExpired(active)) {
    if (pathname.startsWith("/api/")) {
      return clearSession(NextResponse.json({ error: "Session expired — log in again" }, { status: 401 }));
    }
    const login = req.nextUrl.clone();
    login.pathname = "/login";
    login.search = "";
    return clearSession(NextResponse.redirect(login));
  }

  const res = NextResponse.next();
  const secure = process.env.NODE_ENV === "production";
  res.cookies.set(ACTIVE_COOKIE, String(Math.floor(Date.now() / 1000)), {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: MAX_AGE_SECONDS,
  });
  return res;
}

export const config = {
  matcher: [
    "/admin",
    "/admin/:path*",
    "/contribute",
    "/contribute/:path*",
    "/api/admin/:path*",
    "/api/contribute/:path*",
    "/api/audio",
    "/api/audio/:path*",
  ],
};
