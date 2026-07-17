import { requireUser } from "@/lib/auth";
import { backendFetch } from "@/lib/backend";
import { assertSameOrigin } from "@/lib/csrf";
import { clientError, proxyJson } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function POST(req: Request) {
  const forbidden = assertSameOrigin(req);
  if (forbidden) return forbidden;
  try {
    await requireUser();
  } catch {
    return clientError(401, "Login required");
  }
  const token = await getToken();
  if (!token) return clientError(401, "Login required");
  const body = await req.json().catch(() => ({}));
  const { res, data } = await backendFetch("/crowd/v1/audio/presign", {
    method: "POST",
    token,
    body: JSON.stringify({
      content_type: body?.contentType || body?.content_type || "audio/webm",
      byte_size: Number(body?.byteSize || body?.byte_size || 0),
    }),
  });
  if (!res.ok) return proxyJson(res, null, "Presign failed");
  return proxyJson(res, data, "Presign failed");
}
