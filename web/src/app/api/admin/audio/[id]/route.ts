import { requireAdmin } from "@/lib/auth";
import { apiBase } from "@/lib/backend";
import { clientError } from "@/lib/http";
import { getToken } from "@/lib/session";

async function proxyAudio(url: string, token: string) {
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) return null;
  const contentType = res.headers.get("Content-Type") || "audio/webm";
  const buf = await res.arrayBuffer();
  return new Response(buf, {
    status: 200,
    headers: {
      "Content-Type": contentType,
      "Cache-Control": "private, no-store",
    },
  });
}

export async function GET(
  req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  try {
    await requireAdmin();
  } catch {
    return clientError(403, "Reviewer / owner only");
  }
  const token = await getToken();
  if (!token) return clientError(403, "Reviewer / owner only");

  const { id } = await ctx.params;
  if (!id || !/^\d+$/.test(id)) return clientError(400, "Invalid id");

  const byId = await proxyAudio(
    `${apiBase()}/crowd/v1/admin/submissions/${encodeURIComponent(id)}/audio`,
    token,
  );
  if (byId) return byId;

  // Optional ?name= fallback when submission path exists but id stream 404s
  const name = new URL(req.url).searchParams.get("name");
  if (name && /^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$/.test(name)) {
    const byName = await proxyAudio(
      `${apiBase()}/crowd/v1/admin/audio-file/${encodeURIComponent(name)}`,
      token,
    );
    if (byName) return byName;
  }

  return clientError(404, "Audio not found");
}
