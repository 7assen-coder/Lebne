/** Shared headers for proxied audio (Safari wants Content-Length + a filename). */

export function audioProxyHeaders(contentType: string, byteLength: number): HeadersInit {
  const mime = (contentType || "audio/wav").split(";")[0].trim() || "audio/wav";
  let ext = "wav";
  if (mime.includes("webm")) ext = "webm";
  else if (mime.includes("mpeg") || mime.includes("mp3")) ext = "mp3";
  else if (mime.includes("mp4") || mime.includes("m4a")) ext = "m4a";
  else if (mime.includes("ogg")) ext = "ogg";
  else if (mime.includes("aac")) ext = "aac";

  return {
    "Content-Type": mime,
    "Content-Length": String(byteLength),
    "Accept-Ranges": "bytes",
    "Cache-Control": "private, no-store",
    "Content-Disposition": `inline; filename="clip.${ext}"`,
  };
}
