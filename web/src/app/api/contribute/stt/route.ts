import { NextResponse } from "next/server";
import { apiBase } from "@/lib/backend";
import { assertSameOrigin } from "@/lib/csrf";
import { clientError } from "@/lib/http";
import { getToken } from "@/lib/session";

/** Stay under typical Vercel serverless body limits (~4.5MB). */
const MAX_STT_BYTES = 4 * 1024 * 1024;

export async function POST(req: Request) {
  const forbidden = assertSameOrigin(req);
  if (forbidden) return forbidden;
  const token = await getToken();
  if (!token) return clientError(401, "Login required");

  const length = Number(req.headers.get("content-length") || 0);
  if (length > MAX_STT_BYTES) {
    return clientError(413, "Audio too large");
  }

  const form = await req.formData();
  const audio = form.get("audio") || form.get("file");
  if (audio instanceof Blob && audio.size > MAX_STT_BYTES) {
    return clientError(413, "Audio too large");
  }

  const res = await fetch(`${apiBase()}/crowd/v1/stt`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
    cache: "no-store",
  });

  if (!res.ok) {
    return clientError(res.status >= 400 && res.status < 600 ? res.status : 502, "STT failed");
  }

  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    return clientError(502, "STT failed");
  }

  // Only expose expected fields
  const payload = data as {
    ok?: boolean;
    audio_path?: string;
    audioPath?: string;
    transcript?: string;
    field?: string;
    sttConfigured?: boolean;
  };
  return NextResponse.json({
    ok: Boolean(payload.ok),
    audio_path: payload.audio_path || payload.audioPath || null,
    audioPath: payload.audioPath || payload.audio_path || null,
    transcript: typeof payload.transcript === "string" ? payload.transcript : "",
    field: payload.field === "answer" ? "answer" : "question",
    sttConfigured: Boolean(payload.sttConfigured),
  });
}
