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
  const mapped = {
    prompt_id: body?.promptId,
    text: body?.text || body?.question,
    answer: body?.answer,
    audio_path: body?.audioPath,
    note: body?.note,
  };
  const { res, data } = await backendFetch("/crowd/v1/submissions", {
    method: "POST",
    token,
    body: JSON.stringify(mapped),
  });
  if (!res.ok) return proxyJson(res, null, "Submit failed");
  const payload = data as { ok?: boolean; progress?: unknown };
  return proxyJson(res, { ok: true, progress: payload.progress }, "Submit failed");
}
