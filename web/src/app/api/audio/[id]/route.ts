import { requireUser } from "@/lib/auth";
import { apiBase } from "@/lib/backend";
import { clientError } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  try {
    await requireUser();
  } catch {
    return clientError(401, "Login required");
  }
  const token = await getToken();
  if (!token) return clientError(401, "Login required");

  const { id } = await ctx.params;
  if (!id || id.length > 40) return clientError(400, "Invalid id");

  const res = await fetch(`${apiBase()}/crowd/v1/audio/${encodeURIComponent(id)}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
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
