import { LOCALES } from "@/lib/auth";
import { backendFetch } from "@/lib/backend";
import { clientError, proxyJson } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function GET(req: Request) {
  const token = await getToken();
  if (!token) return clientError(401, "Login required");
  const raw = new URL(req.url).searchParams.get("view") || "en";
  const view = (LOCALES as readonly string[]).includes(raw) ? raw : "en";
  const { res, data } = await backendFetch(
    `/crowd/v1/prompts/next?view=${encodeURIComponent(view)}`,
    { token },
  );
  if (!res.ok) return proxyJson(res, null, "Could not load prompt");
  return proxyJson(res, data, "Could not load prompt");
}
