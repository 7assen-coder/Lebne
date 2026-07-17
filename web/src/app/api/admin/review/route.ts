import { requireAdmin } from "@/lib/auth";
import { backendFetch } from "@/lib/backend";
import { assertSameOrigin } from "@/lib/csrf";
import { clientError, proxyJson } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function POST(req: Request) {
  const forbidden = assertSameOrigin(req);
  if (forbidden) return forbidden;
  try {
    await requireAdmin();
  } catch {
    return clientError(403, "Reviewer / owner only");
  }
  const token = await getToken();
  if (!token) return clientError(403, "Reviewer / owner only");
  const body = await req.json().catch(() => null);
  const mapped = {
    submission_id: Number(body?.submissionId),
    action: body?.action,
    text: body?.text,
    answer: body?.answer,
  };
  const { res, data } = await backendFetch("/crowd/v1/admin/review", {
    method: "POST",
    token,
    body: JSON.stringify(mapped),
  });
  if (!res.ok) return proxyJson(res, null, "Review failed");
  return proxyJson(res, data, "Review failed");
}
