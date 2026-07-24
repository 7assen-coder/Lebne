import chipsFallback from "@/data/phrase_chips.json";
import pairsFallback from "@/data/suggest_pairs_fallback.json";
import { backendFetch } from "@/lib/backend";
import { clientError, proxyJson } from "@/lib/http";
import { getToken } from "@/lib/session";

type Pair = { user?: string; hassaniya?: string; tier?: string };

function tokens(text: string): Set<string> {
  const out = new Set<string>();
  for (const m of text.toLowerCase().match(/[\u0600-\u06FF]{2,}|[a-z0-9à-ÿ]{3,}/gi) || []) {
    out.add(m.toLowerCase());
  }
  return out;
}

function localSuggest(q: string) {
  const qToks = tokens(q);
  const scored: { score: number; row: Pair }[] = [];
  for (const row of pairsFallback as Pair[]) {
    const u = String(row.user || "");
    const h = String(row.hassaniya || "").trim();
    if (!u || !h) continue;
    const t = tokens(u);
    let overlap = 0;
    for (const x of qToks) if (t.has(x)) overlap += 1;
    if (overlap <= 0) continue;
    let score = overlap / (qToks.size + t.size - overlap || 1);
    if (row.tier === "gold") score += 0.15;
    scored.push({ score, row });
  }
  scored.sort((a, b) => b.score - a.score);
  const items = scored.slice(0, 5).map(({ score, row }) => ({
    user: row.user,
    hassaniya: row.hassaniya,
    tier: row.tier || "gold",
    score: Math.round(score * 1000) / 1000,
  }));
  const sourceWords: { phrase: string; kind: string; tier: string }[] = [];
  const seen = new Set<string>();
  const add = (phrase: string, kind: string, tier: string) => {
    const p = phrase.trim();
    if (p.length < 2 || seen.has(p)) return;
    seen.add(p);
    sourceWords.push({ phrase: p, kind, tier });
  };
  for (const it of items) {
    add(String(it.hassaniya), "line", String(it.tier));
    for (const tok of String(it.hassaniya).match(/[\u0600-\u06FF]{3,}/g) || []) {
      add(tok, "word", "from_match");
    }
  }
  const chips = (chipsFallback as { chips?: { phrase?: string; tier?: string }[] }).chips || [];
  for (const c of chips.slice(0, 24)) {
    if ((c.tier || "") === "gold") add(String(c.phrase || ""), "chip", "gold");
  }
  const templates = (chipsFallback as { templates?: { pattern?: string }[] }).templates || [];
  return {
    ok: true,
    draft: items[0]
      ? { text: items[0].hassaniya, source: "similar_pair", has_slot: false }
      : null,
    items,
    templates: templates.slice(0, 6).map((t, i) => ({
      id: `t${i}`,
      pattern: t.pattern,
      has_slot: String(t.pattern || "").includes("[X]"),
    })),
    dialectHints: [],
    sourceWords: sourceWords.slice(0, 20),
    fallback: true,
  };
}

export async function GET(req: Request) {
  const token = await getToken();
  if (!token) return clientError(401, "Login required");

  const url = new URL(req.url);
  const q = url.searchParams.get("q") || "";
  const limit = url.searchParams.get("limit") || "3";
  const mine = url.searchParams.get("mine");

  if (mine === "1") {
    const { res, data } = await backendFetch(
      `/crowd/v1/assist/my-phrases?limit=${encodeURIComponent(limit || "40")}`,
      { token },
    );
    if (res.ok) return proxyJson(res, data, "My phrases failed");
    // No backend yet — empty list (user has no server-side history on this deploy)
    return Response.json({ ok: true, phrases: [], submissionCount: 0, fallback: true });
  }

  if (q.trim()) {
    const { res, data } = await backendFetch(
      `/crowd/v1/assist/suggest?q=${encodeURIComponent(q)}&limit=${encodeURIComponent(limit)}`,
      { token },
    );
    if (res.ok) return proxyJson(res, data, "Suggest failed");
    return Response.json(localSuggest(q));
  }

  const { res, data } = await backendFetch("/crowd/v1/assist/chips", { token });
  if (res.ok) return proxyJson(res, data, "Chips failed");
  return Response.json({ ok: true, ...(chipsFallback as object), fallback: true });
}
