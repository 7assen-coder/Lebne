/** Upload a recorded/selected clip to durable storage (R2 presign or multipart). */

export type VoiceUploadResult = {
  audioId: string;
  transcript?: string;
};

const MIME_CANDIDATES = [
  // Prefer mp4/aac; Chrome often only supports webm — we convert to WAV before upload.
  "audio/mp4",
  "audio/aac",
  "audio/webm;codecs=opus",
  "audio/webm",
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

/** Safari cannot play WebM from Chrome. Normalize uploads to WAV for all browsers. */
export async function toUniversalWav(blob: Blob): Promise<Blob> {
  if ((blob.type || "").includes("wav")) return blob;
  const AC =
    typeof window !== "undefined"
      ? window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      : undefined;
  if (!AC) return blob;

  const ctx = new AC();
  try {
    const raw = await blob.arrayBuffer();
    const decoded = await ctx.decodeAudioData(raw.slice(0));
    const targetRate = 22050;
    const frames = Math.max(1, Math.ceil(decoded.duration * targetRate));
    const offline = new OfflineAudioContext(1, frames, targetRate);
    const src = offline.createBufferSource();
    src.buffer = decoded;
    src.connect(offline.destination);
    src.start(0);
    const rendered = await offline.startRendering();
    return audioBufferToWav(rendered);
  } catch {
    return blob;
  } finally {
    try {
      await ctx.close();
    } catch {
      /* ignore */
    }
  }
}

function audioBufferToWav(buffer: AudioBuffer): Blob {
  const sampleRate = buffer.sampleRate;
  const samples = buffer.length;
  const channels = buffer.numberOfChannels;
  const mono = new Float32Array(samples);
  for (let ch = 0; ch < channels; ch++) {
    const data = buffer.getChannelData(ch);
    for (let i = 0; i < samples; i++) mono[i] += data[i] / channels;
  }

  const dataSize = samples * 2;
  const ab = new ArrayBuffer(44 + dataSize);
  const view = new DataView(ab);
  const writeStr = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, dataSize, true);
  let offset = 44;
  for (let i = 0; i < samples; i++) {
    const s = Math.max(-1, Math.min(1, mono[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }
  return new Blob([ab], { type: "audio/wav" });
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
 * 1) Convert to WAV when possible (Safari + Chrome can both play)
 * 2) STT path (asset + optional transcript)
 * 3) R2 presigned PUT when configured
 * 4) Multipart /api/audio (Neon fallback)
 */
export async function uploadVoiceBlob(
  blob: Blob,
  opts?: { withStt?: boolean },
): Promise<VoiceUploadResult> {
  const playable = await toUniversalWav(blob);
  const mime = (playable.type || "audio/wav").split(";")[0];
  const underSttCap = playable.size < 3.5 * 1024 * 1024;

  if (opts?.withStt !== false && underSttCap) {
    try {
      return await sttUpload(playable, mime);
    } catch {
      /* try other paths */
    }
  }

  const presignRes = await fetch("/api/audio/presign", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contentType: mime, byteSize: playable.size }),
  });
  if (presignRes.ok) {
    const presign = await presignRes.json().catch(() => ({}));
    const upload = presign.upload || {};
    if (presign.audioId && upload.url && !upload.useMultipart && upload.method !== "MULTIPART") {
      const putRes = await fetch(upload.url as string, {
        method: "PUT",
        headers: upload.headers || { "Content-Type": mime },
        body: playable,
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

  return multipartUpload(playable, mime);
}
