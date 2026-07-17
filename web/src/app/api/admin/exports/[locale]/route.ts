import { LOCALES, requireOwner } from "@/lib/auth";
import { apiBase } from "@/lib/backend";
import { clientError } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ locale: string }> },
) {
  try {
    await requireOwner();
  } catch {
    return clientError(403, "Owner only");
  }
  const token = await getToken();
  if (!token) return clientError(403, "Owner only");

  const { locale: raw } = await ctx.params;
  const locale = raw.toLowerCase().trim();
  if (!(LOCALES as readonly string[]).includes(locale)) {
    return clientError(400, "Invalid locale");
  }

  const res = await fetch(
    `${apiBase()}/crowd/v1/admin/exports/${encodeURIComponent(locale)}`,
    {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    },
  );
  if (!res.ok) {
    return clientError(
      res.status === 404 ? 404 : res.status >= 400 && res.status < 600 ? res.status : 502,
      res.status === 404 ? "Export not found" : "Download failed",
    );
  }
  const buf = await res.arrayBuffer();
  return new Response(buf, {
    status: 200,
    headers: {
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "Content-Disposition": `attachment; filename="lebne_mru_${locale}.jsonl"`,
      "Cache-Control": "no-store",
    },
  });
}
