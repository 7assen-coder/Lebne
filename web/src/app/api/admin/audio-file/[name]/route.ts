import { requireAdmin } from "@/lib/auth";
import { apiBase } from "@/lib/backend";
import { clientError } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ name: string }> },
) {
  try {
    await requireAdmin();
  } catch {
    return clientError(403, "Reviewer / owner only");
  }
  const token = await getToken();
  if (!token) return clientError(403, "Reviewer / owner only");

  const { name: raw } = await ctx.params;
  const name = decodeURIComponent(raw || "").split("/").pop() || "";
  if (!name || name.length > 128 || /[^A-Za-z0-9._-]/.test(name)) {
    return clientError(400, "Invalid audio name");
  }

  const res = await fetch(
    `${apiBase()}/crowd/v1/admin/audio-file/${encodeURIComponent(name)}`,
    {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    },
  );
  if (!res.ok) {
    return clientError(
      res.status === 404 ? 404 : res.status >= 400 && res.status < 600 ? res.status : 502,
      res.status === 404 ? "Audio not found" : "Audio failed",
    );
  }

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
