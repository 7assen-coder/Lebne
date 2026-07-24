import chipsFallback from "@/data/phrase_chips.json";
import fromSourceExtra from "@/data/from_source_extra.json";
import pairsFallback from "@/data/suggest_pairs_fallback.json";
import { backendFetch } from "@/lib/backend";
import { clientError, proxyJson } from "@/lib/http";
import { getToken } from "@/lib/session";

type Pair = { user?: string; hassaniya?: string; tier?: string; source?: string };
type LineRow = { text?: string; tier?: string; source?: string };

const STOP = new Set([
  "a",
  "an",
  "and",
  "au",
  "can",
  "de",
  "des",
  "du",
  "en",
  "et",
  "for",
  "il",
  "is",
  "je",
  "la",
  "le",
  "les",
  "mon",
  "my",
  "of",
  "peux",
  "que",
  "sans",
  "the",
  "to",
  "un",
  "une",
  "you",
  "y",
]);

/** FR/EN banking stems → Arabic for local corpus/banking match (mirrors assist_util). */
const BRIDGE: Record<string, string[]> = {
  limite: ["حد", "سقف"],
  limit: ["حد", "سقف"],
  montant: ["مبلغ", "فظت", "فلوس"],
  amount: ["مبلغ"],
  retirer: ["سحب", "نسحب"],
  withdraw: ["سحب", "نسحب"],
  retrait: ["سحب"],
  compte: ["حساب", "كونتي"],
  account: ["حساب", "كونتي"],
  facturé: ["رسوم", "عمولة"],
  charged: ["رسوم"],
  frais: ["رسوم", "عمولة"],
  fee: ["رسوم"],
  carte: ["كرت", "بطاقة"],
  card: ["كرت", "بطاقة"],
  solde: ["رصيد", "فظت"],
  balance: ["رصيد"],
  transfert: ["تحويل"],
  transfer: ["تحويل"],
  virement: ["تحويل"],
};

function tokens(text: string): Set<string> {
  const out = new Set<string>();
  for (const m of text.toLowerCase().match(/[\u0600-\u06FF]{2,}|[a-z0-9à-ÿ]{3,}/gi) || []) {
    const t = m.toLowerCase();
    if (!STOP.has(t)) out.add(t);
  }
  const blob = text.toLowerCase();
  for (const [src, targets] of Object.entries(BRIDGE)) {
    if (blob.includes(src) || out.has(src)) {
      out.add(src);
      for (const t of targets) out.add(t);
    }
  }
  return out;
}

function rankLines(qToks: Set<string>, rows: LineRow[], limit: number) {
  const scored: { score: number; row: LineRow }[] = [];
  for (const row of rows) {
    const t = tokens(String(row.text || ""));
    let overlap = 0;
    for (const x of qToks) if (t.has(x)) overlap += 1;
    if (overlap <= 0) continue;
    scored.push({ score: overlap / (qToks.size + t.size - overlap || 1), row });
  }
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, limit).map((s) => s.row);
}

function localSuggest(q: string) {
  const qToks = tokens(q);
  const scored: { score: number; row: Pair }[] = [];
  for (const row of pairsFallback as Pair[]) {
    const u = String(row.user || "");
    const h = String(row.hassaniya || "").trim();
    if (!u || !h) continue;
    const t = tokens(u);
    const ht = tokens(h);
    let overlap = 0;
    for (const x of qToks) {
      if (t.has(x)) overlap += 1;
      else if (ht.has(x)) overlap += 0.5;
    }
    if (overlap <= 0) continue;
    let score = overlap / (qToks.size + t.size - overlap || 1);
    if (row.tier === "hassaniya_corpus") score += 0.1;
    if (row.tier === "gold") score += 0.08;
    scored.push({ score, row });
  }
  scored.sort((a, b) => b.score - a.score);
  const corpus = scored.filter((s) => s.row.tier === "hassaniya_corpus").slice(0, 3);
  const gold = scored.filter((s) => s.row.tier === "gold").slice(0, 2);
  const mixed = [...corpus, ...gold, ...scored].slice(0, 5);
  const seenHs = new Set<string>();
  const items = mixed
    .filter(({ row }) => {
      const h = String(row.hassaniya || "");
      if (seenHs.has(h)) return false;
      seenHs.add(h);
      return true;
    })
    .slice(0, 5)
    .map(({ score, row }) => ({
      user: row.user,
      hassaniya: row.hassaniya,
      tier: row.tier || "gold",
      source: row.source,
      score: Math.round(score * 1000) / 1000,
    }));

  const extra = fromSourceExtra as { banking?: LineRow[]; hassaniya_lines?: LineRow[] };
  const hsLines = rankLines(qToks, extra.hassaniya_lines || [], 6);
  const banking = rankLines(qToks, extra.banking || [], 5);

  const sourceWords: { phrase: string; kind: string; tier: string }[] = [];
  const seen = new Set<string>();
  const add = (phrase: string, kind: string, tier: string) => {
    const p = phrase.trim();
    if (p.length < 2 || p.length > 160 || seen.has(p)) return;
    seen.add(p);
    sourceWords.push({ phrase: p, kind, tier });
  };
  for (const it of items.filter((i) => i.tier === "hassaniya_corpus")) {
    add(String(it.hassaniya), "line", "hassaniya_corpus");
  }
  for (const row of hsLines) add(String(row.text || ""), "line", "hassaniya_corpus");
  for (const row of banking) add(String(row.text || ""), "banking", "banking");
  for (const it of items.filter((i) => i.tier === "gold")) {
    add(String(it.hassaniya), "line", "gold");
  }
  const chips = (chipsFallback as { chips?: { phrase?: string; tier?: string }[] }).chips || [];
  for (const prefer of ["hassaniya_corpus", "banking", "gold"] as const) {
    for (const c of chips) {
      if ((c.tier || "") === prefer) add(String(c.phrase || ""), "chip", prefer);
    }
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
    bankingHints: banking.map((r) => ({ text: r.text, tier: "banking", source: r.source })),
    hassaniyaLines: hsLines.map((r) => ({
      text: r.text,
      tier: "hassaniya_corpus",
      source: r.source,
    })),
    sourceWords: sourceWords.slice(0, 28),
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
