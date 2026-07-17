import { cookies } from "next/headers";

const COOKIE = "lebne_crowd_token";
const ACTIVE_COOKIE = "lebne_crowd_active";

/** Absolute JWT/cookie lifetime — keep in sync with LEBNE_CROWD_TOKEN_TTL_HOURS (default 12). */
const MAX_AGE_SECONDS = Number(process.env.LEBNE_CROWD_TOKEN_TTL_HOURS || 12) * 60 * 60;

/** Sliding idle window — keep in sync with LEBNE_CROWD_IDLE_SECONDS (default 600). */
export const IDLE_SECONDS = Number(process.env.LEBNE_CROWD_IDLE_SECONDS || 600);

export { COOKIE as SESSION_COOKIE, ACTIVE_COOKIE };

export async function getToken() {
  const jar = await cookies();
  return jar.get(COOKIE)?.value || null;
}

export async function setToken(token: string) {
  const jar = await cookies();
  const secure = process.env.NODE_ENV === "production";
  jar.set(COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: MAX_AGE_SECONDS,
  });
  jar.set(ACTIVE_COOKIE, String(Math.floor(Date.now() / 1000)), {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: MAX_AGE_SECONDS,
  });
}

export async function touchActivity() {
  const jar = await cookies();
  if (!jar.get(COOKIE)?.value) return;
  jar.set(ACTIVE_COOKIE, String(Math.floor(Date.now() / 1000)), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: MAX_AGE_SECONDS,
  });
}

export async function clearToken() {
  const jar = await cookies();
  const secure = process.env.NODE_ENV === "production";
  const clear = { httpOnly: true as const, sameSite: "lax" as const, secure, path: "/", maxAge: 0 };
  jar.set(COOKIE, "", clear);
  jar.set(ACTIVE_COOKIE, "", clear);
}

export function isIdleExpired(activeRaw: string | undefined, nowSeconds = Math.floor(Date.now() / 1000)) {
  if (!activeRaw) return true;
  const ts = Number(activeRaw);
  if (!Number.isFinite(ts)) return true;
  return nowSeconds - ts > IDLE_SECONDS;
}
