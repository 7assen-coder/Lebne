"""Contribute assist: chips, slot templates, suggest drafts, dialect hints."""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("lebne.crowd.assist")

ASSIST_DIR = Path("data/assist")
AR_TOKEN = re.compile(r"[\u0600-\u06FF]{2,}|[A-Za-z0-9À-ÿ]{3,}")
SLOT_MARK = "[X]"
# Templates are mined at build time into phrase_chips.json (no static seed list).

# Bridge FR/EN/AR source words → Arabic/Hassaniya stems for corpus matching.
_DOMAIN_BRIDGE: dict[str, tuple[str, ...]] = {
    "limite": ("حد", "سقف", "حدية"),
    "limit": ("حد", "سقف"),
    "montant": ("مبلغ", "فظت", "فلوس"),
    "amount": ("مبلغ", "فظت"),
    "retirer": ("سحب", "نسحب", "نخرج"),
    "withdraw": ("سحب", "نسحب"),
    "retrait": ("سحب",),
    "compte": ("حساب", "كونتي"),
    "account": ("حساب", "كونتي"),
    "facturé": ("رسوم", "تكلفة", "عمولة"),
    "charged": ("رسوم", "عمولة"),
    "frais": ("رسوم", "عمولة"),
    "fee": ("رسوم", "عمولة"),
    "fees": ("رسوم", "عمولة"),
    "carte": ("كرت", "كرتي", "بطاقة"),
    "card": ("كرت", "كرتي", "بطاقة"),
    "solde": ("رصيد", "فظت"),
    "balance": ("رصيد", "فظت"),
    "transfert": ("تحويل", "تحويله", "نحول"),
    "transfer": ("تحويل", "تحويله", "نحول"),
    "virement": ("تحويل", "تحويله"),
    "pin": ("رمز", "سر", "رقم"),
    "password": ("كلمة", "سر"),
    "chino": ("صين",),
    "chine": ("صين",),
    "china": ("صين",),
    "temps": ("وقت", "لاه"),
    "time": ("وقت", "لاه"),
    "combien": ("كم", "شحال"),
    "how": ("كم", "كيف"),
    "long": ("وقت",),
    "activer": ("نشغل", "نفعل", "تفعيل"),
    "activate": ("نشغل", "نفعل"),
    "bloquer": ("نوقف", "نجمد", "بلوك"),
    "block": ("نوقف", "نجمد"),
    "perdue": ("ضاع", "فرقت", "سُرق"),
    "lost": ("ضاع", "فرقت"),
    "échange": ("نبدل", "صرف"),
    "exchange": ("نبدل", "صرف"),
}


# Function words that create false overlaps across FR/EN banking prompts.
_STOPWORDS = {
    "a",
    "an",
    "and",
    "au",
    "aux",
    "can",
    "ce",
    "ces",
    "dans",
    "de",
    "des",
    "du",
    "en",
    "et",
    "être",
    "for",
    "from",
    "il",
    "is",
    "je",
    "la",
    "le",
    "les",
    "mon",
    "my",
    "of",
    "ou",
    "peux",
    "que",
    "qui",
    "sans",
    "sur",
    "the",
    "to",
    "un",
    "une",
    "you",
    "your",
    "y",
}


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in AR_TOKEN.findall(text or "")}


def _content_tokens(text: str) -> set[str]:
    return {t for t in _tokens(text) if t not in _STOPWORDS and len(t) >= 3}


def _query_tokens(text: str) -> set[str]:
    """Content tokens from the source plus domain bridges into Arabic/Hassaniya stems."""
    q = _content_tokens(text)
    blob = _norm(text)
    expanded = set(q)
    for src, targets in _DOMAIN_BRIDGE.items():
        if src in blob or src in q:
            expanded.update(targets)
            expanded.add(src)
    return expanded


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


@lru_cache(maxsize=1)
def load_chips() -> dict:
    path = ASSIST_DIR / "phrase_chips.json"
    if not path.is_file():
        return {"version": 1, "chips": [], "templates": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "chips": [], "templates": []}
    chips = data.get("chips") if isinstance(data, dict) else []
    if not isinstance(chips, list):
        chips = []
    templates = data.get("templates") if isinstance(data, dict) else None
    if not isinstance(templates, list):
        templates = []
    return {
        "version": int(data.get("version") or 1) if isinstance(data, dict) else 1,
        "chips": [
            {
                "phrase": str(c.get("phrase") or "").strip(),
                "tier": c.get("tier") or "gold",
                "source": c.get("source"),
            }
            for c in chips
            if isinstance(c, dict) and str(c.get("phrase") or "").strip()
        ],
        "templates": [
            {
                "id": str(t.get("id") or f"t{i}"),
                "pattern": str(t.get("pattern") or "").strip(),
                "keywords": [str(k).lower() for k in (t.get("keywords") or []) if str(k).strip()],
                "accept_as_is": bool(t.get("accept_as_is")),
            }
            for i, t in enumerate(templates)
            if isinstance(t, dict) and str(t.get("pattern") or "").strip()
        ],
    }


@lru_cache(maxsize=1)
def _suggest_index() -> list[tuple[set[str], dict]]:
    path = ASSIST_DIR / "suggest_pairs.jsonl"
    if not path.is_file():
        return []
    out: list[tuple[set[str], dict]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                user = str(row.get("user") or "").strip()
                hs = str(row.get("hassaniya") or "").strip()
                if not user or not hs:
                    continue
                out.append(
                    (
                        _tokens(user),
                        {
                            "user": user,
                            "hassaniya": hs,
                            "tier": row.get("tier") or "hassaniya_corpus",
                            "source": row.get("source"),
                        },
                    )
                )
    except OSError:
        return []
    return out


def _load_text_index(path: Path, *, tier: str, default_source: str) -> list[tuple[set[str], dict]]:
    if not path.is_file():
        return []
    out: list[tuple[set[str], dict]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = str(row.get("text") or row.get("hassaniya") or "").strip()
                if not text:
                    continue
                out.append(
                    (
                        _tokens(text) | _tokens(str(row.get("user") or "")),
                        {
                            "text": text,
                            "tier": row.get("tier") or tier,
                            "source": row.get("source") or default_source,
                            "dialect": row.get("dialect"),
                        },
                    )
                )
    except OSError:
        return []
    return out


@lru_cache(maxsize=1)
def _dialect_index() -> list[tuple[set[str], dict]]:
    return _load_text_index(
        ASSIST_DIR / "dialect_hints.jsonl",
        tier="dialect_hint",
        default_source="ArBanking77-Tunisian",
    )


@lru_cache(maxsize=1)
def _banking_index() -> list[tuple[set[str], dict]]:
    return _load_text_index(
        ASSIST_DIR / "banking_ar_hints.jsonl",
        tier="banking",
        default_source="imported_banking",
    )


@lru_cache(maxsize=1)
def _hassaniya_line_index() -> list[tuple[set[str], dict]]:
    """Monolingual Hassaniya lines (AI-for-RIM / DAH / DTCD / stories)."""
    return _load_text_index(
        ASSIST_DIR / "hassaniya_lines.jsonl",
        tier="hassaniya_corpus",
        default_source="hassaniya_corpora",
    )


def suggest_for_text(text: str, *, limit: int = 3) -> list[dict]:
    """Return similar Hassaniya rewrites (gold + Hassaniya corpora pairs)."""
    q = _query_tokens(text)
    if not q:
        return []
    scored: list[tuple[float, dict]] = []
    for toks, row in _suggest_index():
        if not toks:
            continue
        # Match on source (user) tokens; also allow overlap with Hassaniya side
        hs_toks = _tokens(str(row.get("hassaniya") or ""))
        user_overlap = len(q & toks)
        hs_overlap = len(q & hs_toks)
        overlap = user_overlap + 0.5 * hs_overlap
        if overlap <= 0:
            continue
        union = len(q | toks) or 1
        score = overlap / union
        tier = row.get("tier") or ""
        if tier == "gold":
            score += 0.12
        elif tier == "hassaniya_corpus":
            score += 0.1
        src = str(row.get("source") or "")
        if "AI-for-RIM" in src or "dah" in src.lower():
            score += 0.04
        scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    out: list[dict] = []
    # Diversify: prefer a mix of corpus + gold so From-source is not gold-only
    buckets: dict[str, list[tuple[float, dict]]] = {"hassaniya_corpus": [], "gold": [], "other": []}
    for score, row in scored:
        tier = str(row.get("tier") or "other")
        buckets.setdefault(tier if tier in buckets else "other", []).append((score, row))

    def push(score: float, row: dict) -> bool:
        hs = row["hassaniya"]
        if hs in seen:
            return False
        seen.add(hs)
        out.append({**row, "score": round(score, 3)})
        return True

    corpus_n = max(1, (limit * 2) // 3)
    gold_n = max(1, limit - corpus_n)
    for score, row in buckets.get("hassaniya_corpus") or []:
        if sum(1 for x in out if x.get("tier") == "hassaniya_corpus") >= corpus_n:
            break
        push(score, row)
    for score, row in buckets.get("gold") or []:
        if sum(1 for x in out if x.get("tier") == "gold") >= gold_n:
            break
        push(score, row)
    for score, row in scored:
        if len(out) >= limit:
            break
        push(score, row)
    return out[:limit]


def _rank_text_index(
    text: str,
    index: list[tuple[set[str], dict]],
    *,
    limit: int,
    flag: str | None = None,
) -> list[dict]:
    q = _query_tokens(text)
    if not q:
        return []
    scored: list[tuple[float, dict]] = []
    for toks, row in index:
        if not toks:
            continue
        overlap = len(q & toks)
        if overlap <= 0:
            continue
        score = overlap / (len(q | toks) or 1)
        scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    out: list[dict] = []
    for score, row in scored:
        t = row["text"]
        if t in seen:
            continue
        seen.add(t)
        item = {**row, "score": round(score, 3)}
        if flag:
            item["flag"] = flag
        out.append(item)
        if len(out) >= limit:
            break
    return out


def dialect_hints_for_text(text: str, *, limit: int = 2) -> list[dict]:
    """Tunisian/etc. banking lines — scaffolding only, never auto-train."""
    return _rank_text_index(text, _dialect_index(), limit=limit, flag="dialect_hint")


def banking_hints_for_text(text: str, *, limit: int = 4) -> list[dict]:
    """Banking Arabic (MSA) lines from Banking77 / ArBanking77 — suggestion-only."""
    return _rank_text_index(text, _banking_index(), limit=limit, flag="banking")


def hassaniya_lines_for_text(text: str, *, limit: int = 6) -> list[dict]:
    """Pure Hassaniya corpus lines (RIM / DAH / DTCD / stories)."""
    return _rank_text_index(text, _hassaniya_line_index(), limit=limit, flag="hassaniya_corpus")


def match_templates(text: str, *, limit: int = 3) -> list[dict]:
    """Rank mined slot templates by keyword / token overlap with the source prompt."""
    blob = _norm(text)
    qtoks = _tokens(text)
    ranked: list[tuple[int, dict]] = []
    for t in load_chips().get("templates") or []:
        kws = [str(k).lower() for k in (t.get("keywords") or []) if str(k).strip()]
        pattern = str(t.get("pattern") or "")
        # Also score on Arabic tokens from the template pattern itself
        pattern_toks = _tokens(pattern.replace(SLOT_MARK, " "))
        hits = sum(1 for k in kws if k and k in blob)
        hits += len(qtoks & pattern_toks)
        if hits <= 0:
            continue
        fixed = pattern.replace(SLOT_MARK, "").strip()
        ranked.append(
            (
                hits,
                {
                    "id": t.get("id"),
                    "pattern": pattern,
                    "fixed": fixed,
                    "has_slot": SLOT_MARK in pattern,
                    "accept_as_is": bool(t.get("accept_as_is")),
                    "hits": hits,
                },
            )
        )
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [row for _, row in ranked[:limit]]


def fill_template(pattern: str, slot_value: str | None = None) -> str:
    pattern = (pattern or "").strip()
    if SLOT_MARK not in pattern:
        return pattern
    slot = (slot_value or "").strip()
    if not slot:
        return pattern  # leave [X] visible for editing
    return pattern.replace(SLOT_MARK, slot).replace("  ", " ").strip()


def _guess_slot_from_source(text: str) -> str:
    """Lightweight slot fill: keep a short distinctive chunk from the source."""
    t = (text or "").strip()
    if not t:
        return ""
    # Prefer trailing "from X" / "من X"
    m = re.search(r"(?i)\bfrom\s+([A-Za-z\u0600-\u06FF][\w\u0600-\u06FF\s-]{1,40})", t)
    if m:
        return m.group(1).strip()
    m = re.search(r"من\s+([\u0600-\u06FFA-Za-z][\u0600-\u06FFA-Za-z\s-]{1,40})", t)
    if m:
        return m.group(1).strip(" ؟?.!")
    # Card-ish: last few arabic tokens
    ar = re.findall(r"[\u0600-\u06FF]+", t)
    if len(ar) >= 2:
        return " ".join(ar[-3:])
    words = t.split()
    if len(words) <= 6:
        return t
    return " ".join(words[-4:]).strip(" ?!.")


def _ollama_rewrite(text: str) -> str | None:
    """Optional local few-shot rewrite via Ollama (lebne-hassaniya)."""
    base = (os.environ.get("LEBNE_ASSIST_OLLAMA_BASE") or "").strip()
    if not base:
        # Local default only — never assume Ollama on Render
        if os.environ.get("LEBNE_ASSIST_USE_OLLAMA", "").lower() in {"1", "true", "yes"}:
            base = "http://127.0.0.1:11434/v1"
        else:
            return None
    model = (os.environ.get("LEBNE_ASSIST_OLLAMA_MODEL") or "lebne-hassaniya").strip()
    # Few-shot from top gold pairs
    shots = suggest_for_text(text, limit=4)
    lines = [
        "Rewrite the user message into ONE natural Mauritanian Hassaniya banking phrase.",
        "Output Hassaniya only. No explanation.",
        "",
    ]
    for s in shots:
        lines.append(f"Q: {s['user']}")
        lines.append(f"A: {s['hassaniya']}")
        lines.append("")
    lines.append(f"Q: {text.strip()}")
    lines.append("A:")
    prompt = "\n".join(lines)
    body = json.dumps(
        {
            "model": model,
            "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            data = json.loads(res.read().decode("utf-8"))
        out = (data["choices"][0]["message"]["content"] or "").strip()
        # Keep first line only
        out = out.splitlines()[0].strip().strip('"')
        if len(out) < 2:
            return None
        return out
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as exc:
        log.info("ollama_draft_skip err=%s", exc)
        return None


def build_draft(text: str) -> dict:
    """Build a suggestion-only draft: Ollama → gold pair → template fill."""
    text = (text or "").strip()
    items = suggest_for_text(text, limit=3)
    templates = match_templates(text, limit=3)
    dialect = dialect_hints_for_text(text, limit=2)

    ollama = _ollama_rewrite(text) if text else None
    if ollama:
        draft = {
            "text": ollama,
            "source": "ollama",
            "fixed": "",
            "slot": "",
            "has_slot": False,
        }
    elif items:
        draft = {
            "text": items[0]["hassaniya"],
            "source": "similar_pair",
            "fixed": "",
            "slot": "",
            "has_slot": False,
            "pair_user": items[0].get("user"),
        }
    elif templates:
        tmpl = templates[0]
        slot = "" if tmpl.get("accept_as_is") else _guess_slot_from_source(text)
        filled = fill_template(tmpl["pattern"], None if tmpl.get("accept_as_is") else slot or None)
        # If still has [X], keep pattern as draft with slot empty for UI
        if SLOT_MARK in filled:
            draft = {
                "text": filled,
                "source": "template",
                "fixed": tmpl.get("fixed") or "",
                "slot": "",
                "has_slot": True,
                "template_id": tmpl.get("id"),
                "pattern": tmpl["pattern"],
            }
        else:
            draft = {
                "text": filled if SLOT_MARK not in tmpl["pattern"] else fill_template(tmpl["pattern"], slot),
                "source": "template",
                "fixed": tmpl.get("fixed") or "",
                "slot": slot,
                "has_slot": bool(tmpl.get("has_slot")),
                "template_id": tmpl.get("id"),
                "pattern": tmpl["pattern"],
            }
            if tmpl.get("accept_as_is"):
                draft["text"] = tmpl["pattern"].replace(SLOT_MARK, "").strip()
                draft["has_slot"] = False
    else:
        draft = None

    return {
        "draft": draft,
        "items": items,
        "templates": templates,
        "dialectHints": dialect,
        "bankingHints": banking_hints_for_text(text, limit=4),
        "hassaniyaLines": hassaniya_lines_for_text(text, limit=6),
    }


def highlight_parts(draft_text: str, fixed: str) -> dict:
    """Split draft into fixed prefix vs editable remainder for UI highlight."""
    text = (draft_text or "").strip()
    fix = (fixed or "").strip()
    if fix and text.startswith(fix):
        return {"fixed": fix, "editable": text[len(fix) :].strip()}
    if SLOT_MARK in text:
        left, _, right = text.partition(SLOT_MARK)
        return {"fixed": left.strip(), "editable": right.strip(), "slot_mark": True}
    return {"fixed": "", "editable": text}


def mine_my_phrases(texts: list[str], *, min_count: int = 2, top_k: int = 40) -> list[dict]:
    """Mine repeated Hassaniya phrases from one contributor's past submissions."""
    from collections import Counter

    ar = re.compile(r"[\u0600-\u06FF]{2,}")
    c1: Counter[str] = Counter()
    c2: Counter[str] = Counter()
    c3: Counter[str] = Counter()
    for text in texts:
        toks = ar.findall(text or "")
        for t in toks:
            if len(t) >= 3:
                c1[t] += 1
        for i in range(len(toks) - 1):
            c2[" ".join(toks[i : i + 2])] += 1
        for i in range(len(toks) - 2):
            c3[" ".join(toks[i : i + 3])] += 1
    out: list[dict] = []
    seen: set[str] = set()
    for ngram, counter in ((3, c3), (2, c2), (1, c1)):
        for phrase, n in counter.most_common(top_k):
            if n < min_count or phrase in seen:
                continue
            seen.add(phrase)
            out.append({"phrase": phrase, "count": n, "n": ngram, "tier": "mine"})
            if len(out) >= top_k:
                return out
    return out


def source_word_suggestions(text: str, *, limit: int = 28) -> list[dict]:
    """From-source chips: Hassaniya corpora + banking Arabic + gold (suggestion-only).

    Budget slots so gold words never crowd out RIM/DAH/DTCD/stories and banking AR.
    """
    items = suggest_for_text(text, limit=10)
    templates = match_templates(text, limit=3)
    hs_lines = hassaniya_lines_for_text(text, limit=10)
    banking = banking_hints_for_text(text, limit=6)
    dialect = dialect_hints_for_text(text, limit=2)

    out: list[dict] = []
    seen: set[str] = set()

    def add(phrase: str, *, kind: str, tier: str = "suggest") -> bool:
        p = (phrase or "").strip()
        # Keep long lines usable as insertable snippets (cap length in UI separately)
        if len(p) < 2 or len(p) > 160 or p in seen:
            return False
        seen.add(p)
        out.append({"phrase": p, "kind": kind, "tier": tier})
        return True

    def take(n: int, rows: list, *, kind: str, tier: str, key: str = "text") -> None:
        got = 0
        for row in rows:
            if got >= n or len(out) >= limit:
                return
            if add(str(row.get(key) or ""), kind=kind, tier=tier):
                got += 1

    gold_items = [it for it in items if str(it.get("tier") or "") == "gold"]
    corpus_items = [it for it in items if str(it.get("tier") or "") == "hassaniya_corpus"]

    # 1) Hassaniya corpus pairs (AI-for-RIM, dah, …) — priority for From source
    take(5, corpus_items, kind="line", tier="hassaniya_corpus", key="hassaniya")
    # 2) Monolingual Hassaniya (RIM / DAH / DTCD / stories)
    take(6, hs_lines, kind="line", tier="hassaniya_corpus")
    # 3) Banking Arabic (MSA) — scaffold only
    take(5, banking, kind="banking", tier="banking")
    # 4) Gold Lebne pairs
    take(3, gold_items, kind="line", tier="gold", key="hassaniya")

    # 5) A few stems from the best matching lines (not every token)
    for it in (corpus_items[:3] + gold_items[:2]):
        if len(out) >= limit:
            break
        tier = str(it.get("tier") or "hassaniya_corpus")
        toks = re.findall(r"[\u0600-\u06FF]{3,}", str(it.get("hassaniya") or ""))
        for tok in toks[:3]:
            if len(out) >= limit:
                break
            add(tok.strip("،,.؛:!?؟"), kind="word", tier=tier)

    for t in templates:
        if len(out) >= limit:
            break
        pat = str(t.get("pattern") or "").replace(SLOT_MARK, "").strip()
        add(pat, kind="template", tier="template")

    # 6) Mined chips: corpus + banking + gold
    chips = load_chips().get("chips") or []
    for prefer in ("hassaniya_corpus", "banking", "gold"):
        for c in chips:
            if len(out) >= limit:
                break
            if str(c.get("tier") or "") == prefer:
                add(str(c.get("phrase") or ""), kind="chip", tier=prefer)

    for d in dialect:
        if len(out) >= limit:
            break
        add(str(d.get("text") or ""), kind="dialect", tier="dialect_hint")

    return out[:limit]
