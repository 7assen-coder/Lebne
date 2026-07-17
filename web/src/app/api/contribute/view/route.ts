import { LOCALES } from "@/lib/auth";
import { backendFetch } from "@/lib/backend";
import { clientError, proxyJson } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function GET(req: Request) {
  const token = await getToken();
  if (!token) return clientError(401, "Login required");
  const url = new URL(req.url);
  const promptId = url.searchParams.get("promptId");
  const raw = url.searchParams.get("view") || "en";
  if (!promptId || !/^\d+$/.test(promptId)) {
    return clientError(400, "promptId required");
  }
  const view = (LOCALES as readonly string[]).includes(raw) ? raw : "en";
  const { res, data } = await backendFetch(
    `/crowd/v1/prompts/${encodeURIComponent(promptId)}/view?view=${encodeURIComponent(view)}`,
    { token },
  );
  if (!res.ok) return proxyJson(res, null, "Could not load view");
  return proxyJson(res, data, "Could not load view");
}
