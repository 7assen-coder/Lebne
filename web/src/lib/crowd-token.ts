import { createHmac, timingSafeEqual } from "node:crypto";

type CrowdClaims = {
  sub: string;
  email: string;
  name?: string;
  role?: string;
  is_admin?: boolean;
  tv?: number;
  aud?: string;
  iss?: string;
  exp?: number;
};

function b64urlToBuf(s: string): Buffer {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  return Buffer.from(s.replace(/-/g, "+").replace(/_/g, "/") + pad, "base64");
}

/** Verify crowd JWT locally when LEBNE_JWT_SECRET is set (avoids /auth/me RTT). */
export function readCrowdToken(token: string): CrowdClaims | null {
  const secret = (process.env.LEBNE_JWT_SECRET || "").trim();
  if (!secret || secret.length < 16) return null;

  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const [header, payload, sigB64] = parts;
  const expected = createHmac("sha256", secret).update(`${header}.${payload}`).digest();
  let sig: Buffer;
  try {
    sig = b64urlToBuf(sigB64);
  } catch {
    return null;
  }
  if (sig.length !== expected.length || !timingSafeEqual(sig, expected)) return null;

  let claims: CrowdClaims;
  try {
    claims = JSON.parse(b64urlToBuf(payload).toString("utf8")) as CrowdClaims;
  } catch {
    return null;
  }

  if (claims.aud !== "lebne-crowd") return null;
  const issuer = (process.env.LEBNE_JWT_ISSUER || "lebne").trim();
  if (claims.iss && claims.iss !== issuer) return null;
  if (typeof claims.exp === "number" && claims.exp * 1000 < Date.now()) return null;
  if (!claims.sub || !claims.email) return null;
  return claims;
}
