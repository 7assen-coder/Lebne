import { apiBase } from "@/lib/backend";

/** Ping the API so Render free tier stays warm (Vercel Cron). */
export async function GET(req: Request) {
  const secret = process.env.CRON_SECRET?.trim();
  if (secret) {
    const auth = req.headers.get("authorization") || "";
    if (auth !== `Bearer ${secret}`) {
      return Response.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  const started = Date.now();
  try {
    const res = await fetch(`${apiBase()}/health`, { cache: "no-store" });
    const body = await res.text();
    return Response.json({
      ok: res.ok,
      status: res.status,
      ms: Date.now() - started,
      body: body.slice(0, 200),
    });
  } catch (err) {
    return Response.json(
      {
        ok: false,
        ms: Date.now() - started,
        error: err instanceof Error ? err.message : "ping failed",
      },
      { status: 502 },
    );
  }
}
