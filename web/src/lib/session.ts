import { cookies } from "next/headers";

const COOKIE = "lebne_crowd_token";
/** Keep in sync with LEBNE_CROWD_TOKEN_TTL_DAYS (default 7). */
const MAX_AGE_SECONDS = 60 * 60 * 24 * 7;

export async function getToken() {
  const jar = await cookies();
  return jar.get(COOKIE)?.value || null;
}

export async function setToken(token: string) {
  const jar = await cookies();
  jar.set(COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: MAX_AGE_SECONDS,
  });
}

export async function clearToken() {
  const jar = await cookies();
  jar.set(COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
}
