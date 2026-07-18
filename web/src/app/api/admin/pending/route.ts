import { requireAdmin } from "@/lib/auth";
import { backendFetch } from "@/lib/backend";
import { clientError, proxyJson } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function GET(req: Request) {
  try {
    await requireAdmin();
  } catch {
    return clientError(403, "Reviewer / owner only");
  }
  const token = await getToken();
  if (!token) return clientError(403, "Reviewer / owner only");
  const { searchParams } = new URL(req.url);
  const page = searchParams.get("page") || "1";
  const limit = searchParams.get("limit") || "20";
  const params = new URLSearchParams({ page, limit });
  const { res, data } = await backendFetch(`/crowd/v1/admin/pending?${params}`, { token });
  if (!res.ok) return proxyJson(res, null, "Pending list failed");
  return proxyJson(res, data, "Pending list failed");
}
