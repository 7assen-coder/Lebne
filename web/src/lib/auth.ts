import { backendFetch } from "./backend";
import { readCrowdToken } from "./crowd-token";
import { clearToken, getToken } from "./session";

const LOCALES = ["en", "fr", "ar", "hassaniya"] as const;
export type Locale = (typeof LOCALES)[number];
export { LOCALES };

export type UserRole = "owner" | "reviewer" | "contributor";

export type SessionUser = {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  isAdmin: boolean;
  isReviewer: boolean;
};

function sessionFromClaims(claims: {
  sub: string;
  email: string;
  name?: string;
  role?: string;
  is_admin?: boolean;
}): SessionUser {
  const role = (claims.role as UserRole) || (claims.is_admin ? "owner" : "contributor");
  return {
    id: String(claims.sub),
    name: claims.name || "",
    email: claims.email,
    role,
    isAdmin: Boolean(claims.is_admin || role === "owner"),
    isReviewer: Boolean(role === "owner" || role === "reviewer"),
  };
}

export async function getSession(): Promise<SessionUser | null> {
  const token = await getToken();
  if (!token) return null;

  // Fast path: verify JWT in the Next.js process (no Render round-trip).
  const claims = readCrowdToken(token);
  if (claims) return sessionFromClaims(claims);

  const { res, data } = await backendFetch("/crowd/v1/auth/me", { token });
  if (!res.ok) return null;
  const payload = data as {
    user?: {
      id?: number | string;
      name?: string;
      email?: string;
      role?: string;
      isAdmin?: boolean;
      isReviewer?: boolean;
    };
  };
  const user = payload.user;
  if (!user || user.id == null || !user.email) return null;
  const role = (user.role as UserRole) || (user.isAdmin ? "owner" : "contributor");
  return {
    id: String(user.id),
    name: user.name || "",
    email: user.email,
    role,
    isAdmin: Boolean(user.isAdmin || role === "owner"),
    isReviewer: Boolean(user.isReviewer || role === "owner" || role === "reviewer"),
  };
}

export async function destroySession() {
  await clearToken();
}

export async function requireUser() {
  const user = await getSession();
  if (!user) throw new Error("UNAUTHORIZED");
  return user;
}

/** Reviewer or owner (Inbox). Prefer requireOwner for People / exports / edits. */
export async function requireAdmin() {
  const user = await requireUser();
  if (!user.isReviewer) throw new Error("FORBIDDEN");
  return user;
}

export async function requireOwner() {
  const user = await requireUser();
  if (!user.isAdmin) throw new Error("FORBIDDEN");
  return user;
}
