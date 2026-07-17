import { requireOwner } from "@/lib/auth";
import { backendFetch } from "@/lib/backend";
import { clientError, proxyJson } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function GET() {
  try {
    await requireOwner();
  } catch {
    return clientError(403, "Owner only");
  }
  const token = await getToken();
  if (!token) return clientError(403, "Owner only");
  const { res, data } = await backendFetch("/crowd/v1/admin/exports", { token });
  if (!res.ok) return proxyJson(res, null, "Export list failed");
  return proxyJson(res, data, "Export list failed");
}
