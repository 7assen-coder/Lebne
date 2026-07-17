import { requireOwner } from "@/lib/auth";
import { backendFetch } from "@/lib/backend";
import { assertSameOrigin } from "@/lib/csrf";
import { clientError, proxyJson } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function POST(
  req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const forbidden = assertSameOrigin(req);
  if (forbidden) return forbidden;
  try {
    await requireOwner();
  } catch {
    return clientError(403, "Owner only");
  }
  const token = await getToken();
  if (!token) return clientError(403, "Owner only");
  const { id } = await ctx.params;
  if (!/^\d+$/.test(id)) return clientError(400, "Invalid item");
  const body = await req.json().catch(() => null);
  const text = typeof body?.text === "string" ? body.text.trim() : "";
  if (text.length < 2 || text.length > 2000) {
    return clientError(400, "Invalid text");
  }
  const answer =
    body?.answer == null || body?.answer === ""
      ? null
      : String(body.answer).slice(0, 4000);
  const audioPath =
    typeof body?.audioPath === "string"
      ? body.audioPath.slice(0, 512)
      : typeof body?.audio_path === "string"
        ? body.audio_path.slice(0, 512)
        : undefined;
  const clearAudio = Boolean(body?.clearAudio || body?.clear_audio);
  const { res, data } = await backendFetch(
    `/crowd/v1/admin/approved/${encodeURIComponent(id)}`,
    {
      method: "POST",
      token,
      body: JSON.stringify({
        text,
        answer,
        audio_path: clearAudio ? null : audioPath,
        clear_audio: clearAudio,
      }),
    },
  );
  if (!res.ok) return proxyJson(res, null, "Edit failed");
  return proxyJson(res, data, "Edit failed");
}
