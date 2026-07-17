import { backendFetch } from "@/lib/backend";
import { assertSameOrigin } from "@/lib/csrf";
import { clientError, proxyJson } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function POST(req: Request) {
  const forbidden = assertSameOrigin(req);
  if (forbidden) return forbidden;
  const token = await getToken();
  if (!token) return clientError(401, "Login required");
  const body = await req.json().catch(() => null);
  const { res, data } = await backendFetch("/crowd/v1/prompts/skip", {
    method: "POST",
    token,
    body: JSON.stringify({ prompt_id: body?.promptId }),
  });
  if (!res.ok) return proxyJson(res, null, "Skip failed");
  const payload = data as { ok?: boolean; skipped?: boolean; progress?: unknown };
  return proxyJson(
    res,
    { ok: true, skipped: payload.skipped, progress: payload.progress },
    "Skip failed",
  );
}
