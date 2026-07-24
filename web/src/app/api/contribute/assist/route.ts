import { backendFetch } from "@/lib/backend";
import { clientError, proxyJson } from "@/lib/http";
import { getToken } from "@/lib/session";

export async function GET(req: Request) {
  const token = await getToken();
  if (!token) return clientError(401, "Login required");

  const url = new URL(req.url);
  const q = url.searchParams.get("q") || "";
  const limit = url.searchParams.get("limit") || "3";

  if (q.trim()) {
    const { res, data } = await backendFetch(
      `/crowd/v1/assist/suggest?q=${encodeURIComponent(q)}&limit=${encodeURIComponent(limit)}`,
      { token },
    );
    if (!res.ok) return proxyJson(res, null, "Suggest failed");
    return proxyJson(res, data, "Suggest failed");
  }

  const { res, data } = await backendFetch("/crowd/v1/assist/chips", { token });
  if (!res.ok) return proxyJson(res, null, "Chips failed");
  return proxyJson(res, data, "Chips failed");
}
