/** Upload a recorded/selected clip to durable storage (R2 presign or multipart). */

export type VoiceUploadResult = {
  audioId: string;
  transcript?: string;
};

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/aac",
  "audio/ogg",
];

export function pickRecorderMime(): string {
  if (typeof MediaRecorder === "undefined") return "audio/webm";
  for (const m of MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return "";
}

export function extForMime(mime: string): string {
  const base = mime.split(";")[0].trim().toLowerCase();
  if (base.includes("mp4") || base.includes("m4a") || base.includes("aac")) return "m4a";
  if (base.includes("mpeg") || base.includes("mp3")) return "mp3";
  if (base.includes("ogg")) return "ogg";
  if (base.includes("wav")) return "wav";
  return "webm";
}

async function multipartUpload(blob: Blob, mime: string): Promise<VoiceUploadResult> {
  const fd = new FormData();
  fd.append("audio", blob, `clip.${extForMime(mime)}`);
  const res = await fetch("/api/audio", { method: "POST", body: fd });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.audioId) {
    throw new Error(data.error || "Upload failed");
  }
  return { audioId: String(data.audioId) };
}

async function sttUpload(blob: Blob, mime: string): Promise<VoiceUploadResult> {
  const fd = new FormData();
  fd.append("audio", blob, `clip.${extForMime(mime)}`);
  fd.append("field", "question");
  const res = await fetch("/api/contribute/stt", { method: "POST", body: fd });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.audioId) {
    throw new Error(data.error || "Voice failed");
  }
  return {
    audioId: String(data.audioId),
    transcript: typeof data.transcript === "string" ? data.transcript : undefined,
  };
}

/**
 * Durable upload:
 * 1) STT path (asset + optional transcript) for typical clips
 * 2) R2 presigned PUT when configured (bypasses Vercel body limit)
 * 3) Multipart /api/audio (Neon fallback / small clips)
 */
export async function uploadVoiceBlob(
  blob: Blob,
  opts?: { withStt?: boolean },
): Promise<VoiceUploadResult> {
  const mime = (blob.type || "audio/webm").split(";")[0];
  const underSttCap = blob.size < 3.5 * 1024 * 1024;

  if (opts?.withStt !== false && underSttCap) {
    try {
      return await sttUpload(blob, mime);
    } catch {
      /* try other paths */
    }
  }

  const presignRes = await fetch("/api/audio/presign", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contentType: mime, byteSize: blob.size }),
  });
  if (presignRes.ok) {
    const presign = await presignRes.json().catch(() => ({}));
    const upload = presign.upload || {};
    if (presign.audioId && upload.url && !upload.useMultipart && upload.method !== "MULTIPART") {
      const putRes = await fetch(upload.url as string, {
        method: "PUT",
        headers: upload.headers || { "Content-Type": mime },
        body: blob,
      });
      if (!putRes.ok) throw new Error("Direct upload failed");
      const done = await fetch("/api/audio/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ audioId: presign.audioId }),
      });
      if (!done.ok) {
        const err = await done.json().catch(() => ({}));
        throw new Error(err.error || "Could not finalize upload");
      }
      return { audioId: String(presign.audioId) };
    }
  }

  return multipartUpload(blob, mime);
}
