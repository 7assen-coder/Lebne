import { requireOwner } from "@/lib/auth";
import { backendFetch } from "@/lib/backend";
import { clientError, proxyJson } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function GET(req: Request) {
  try {
    await requireOwner();
  } catch {
    return clientError(403, "Owner only");
  }
  const token = await getToken();
  if (!token) return clientError(403, "Owner only");
  const { searchParams } = new URL(req.url);
  const q = searchParams.get("q");
  const page = searchParams.get("page") || "1";
  const limit = searchParams.get("limit") || "20";
  const params = new URLSearchParams();
  if (q) params.set("q", q.slice(0, 200));
  params.set("page", page);
  params.set("limit", limit);
  const { res, data } = await backendFetch(`/crowd/v1/admin/approved?${params}`, { token });
  if (!res.ok) return proxyJson(res, null, "Approved list failed");
  return proxyJson(res, data, "Approved list failed");
}
