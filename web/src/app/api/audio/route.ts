import { NextResponse } from "next/server";
import { apiBase } from "@/lib/backend";
import { assertSameOrigin } from "@/lib/csrf";
import { clientError } from "@/lib/http";
import { getToken } from "@/lib/session";

const MAX_BYTES = 8 * 1024 * 1024;

export async function POST(req: Request) {
  const forbidden = assertSameOrigin(req);
  if (forbidden) return forbidden;
  const token = await getToken();
  if (!token) return clientError(401, "Login required");

  const length = Number(req.headers.get("content-length") || 0);
  if (length > MAX_BYTES) return clientError(413, "Audio too large");

  const form = await req.formData();
  const audio = form.get("audio") || form.get("file");
  if (!(audio instanceof Blob)) return clientError(400, "Missing audio");
  if (audio.size > MAX_BYTES) return clientError(413, "Audio too large");

  const res = await fetch(`${apiBase()}/crowd/v1/audio`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
    cache: "no-store",
  });
  if (!res.ok) {
    return clientError(res.status >= 400 && res.status < 600 ? res.status : 502, "Upload failed");
  }
  const data = await res.json().catch(() => ({}));
  return NextResponse.json({
    ok: true,
    audioId: data.audioId || data.audio_id || null,
    status: data.status,
    ready: Boolean(data.ready),
  });
}
