/** Safari-friendly authenticated audio: fetch → Blob → object URL. */

export async function loadAudioObjectUrl(src: string): Promise<{
  url: string;
  contentType: string;
}> {
  const res = await fetch(src, { cache: "no-store", credentials: "same-origin" });
  if (!res.ok) {
    const err = new Error(`audio_${res.status}`);
    (err as Error & { status: number }).status = res.status;
    throw err;
  }
  const contentType = (res.headers.get("Content-Type") || "audio/wav").split(";")[0];
  const buf = await res.arrayBuffer();
  const blob = new Blob([buf], { type: contentType });
  return { url: URL.createObjectURL(blob), contentType };
}

export function isLikelyUnplayableInSafari(contentType: string): boolean {
  const t = contentType.toLowerCase();
  return t.includes("webm") || t.includes("ogg");
}
