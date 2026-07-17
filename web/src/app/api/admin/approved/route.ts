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
  const qs = q ? `?q=${encodeURIComponent(q.slice(0, 200))}` : "";
  const { res, data } = await backendFetch(`/crowd/v1/admin/approved${qs}`, { token });
  if (!res.ok) return proxyJson(res, null, "Approved list failed");
  return proxyJson(res, data, "Approved list failed");
}
