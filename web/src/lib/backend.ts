/** Server-side client for the Dockerized FastAPI crowd API. Never use NEXT_PUBLIC_* here. */

function resolveApiBase(): string {
  const raw = (process.env.API_INTERNAL_URL || "http://127.0.0.1:8000").trim();
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("API_INTERNAL_URL must be a valid absolute URL");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("API_INTERNAL_URL must use http or https");
  }
  // Prevent accidental path injection via env (always call with absolute paths).
  return url.origin;
}

const API_URL = resolveApiBase();

export function apiBase() {
  return API_URL;
}

export async function backendFetch(
  path: string,
  init: RequestInit & { token?: string } = {},
) {
  if (!path.startsWith("/")) {
    throw new Error("backendFetch path must start with /");
  }
  const { token, headers, ...rest } = init;
  const h = new Headers(headers);
  if (!h.has("Content-Type") && rest.body && !(rest.body instanceof FormData)) {
    h.set("Content-Type", "application/json");
  }
  if (token) h.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${apiBase()}${path}`, { ...rest, headers: h, cache: "no-store" });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  return { res, data };
}
