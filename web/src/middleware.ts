import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const COOKIE = "lebne_crowd_token";

/** Early gate — pages still re-check role via getSession(). */
export function middleware(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value;
  if (token) return NextResponse.next();

  const { pathname } = req.nextUrl;
  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "Login required" }, { status: 401 });
  }

  const login = req.nextUrl.clone();
  login.pathname = "/login";
  login.search = "";
  return NextResponse.redirect(login);
}

export const config = {
  matcher: [
    "/admin",
    "/admin/:path*",
    "/contribute",
    "/contribute/:path*",
    "/api/admin/:path*",
    "/api/contribute/:path*",
  ],
};
