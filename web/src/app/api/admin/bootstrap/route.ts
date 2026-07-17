import { requireAdmin } from "@/lib/auth";
import { backendFetch } from "@/lib/backend";
import { clientError, proxyJson } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function GET() {
  try {
    await requireAdmin();
  } catch {
    return clientError(403, "Reviewer / owner only");
  }
  const token = await getToken();
  if (!token) return clientError(403, "Reviewer / owner only");
  const { res, data } = await backendFetch("/crowd/v1/admin/bootstrap", { token });
  if (!res.ok) return proxyJson(res, null, "Admin load failed");
  return proxyJson(res, data, "Admin load failed");
}
