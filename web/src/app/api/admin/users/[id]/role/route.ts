import { requireOwner } from "@/lib/auth";
import { backendFetch } from "@/lib/backend";
import { assertSameOrigin } from "@/lib/csrf";
import { clientError, proxyJson } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function POST(
  req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const forbidden = assertSameOrigin(req);
  if (forbidden) return forbidden;
  try {
    await requireOwner();
  } catch {
    return clientError(403, "Owner only");
  }
  const token = await getToken();
  if (!token) return clientError(403, "Owner only");
  const { id } = await ctx.params;
  if (!/^\d+$/.test(id)) return clientError(400, "Invalid user");
  const body = await req.json().catch(() => null);
  const role = body?.role;
  if (role !== "reviewer" && role !== "contributor") {
    return clientError(400, "Invalid role");
  }
  const { res, data } = await backendFetch(
    `/crowd/v1/admin/users/${encodeURIComponent(id)}/role`,
    {
      method: "POST",
      token,
      body: JSON.stringify({ role }),
    },
  );
  if (!res.ok) return proxyJson(res, null, "Role update failed");
  return proxyJson(res, data, "Role update failed");
}
