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
AR_TOKEN = re.compile(r"[\u0600-\u06FF]{2,}|[A-Za-z0-9]{3,}")
SLOT_MARK = "[X]"
# Templates are mined at build time into phrase_chips.json (no static seed list).


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in AR_TOKEN.findall(text or "")}


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


@lru_cache(maxsize=1)
def _dialect_index() -> list[tuple[set[str], dict]]:
    path = ASSIST_DIR / "dialect_hints.jsonl"
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
                text = str(row.get("text") or "").strip()
                if not text:
                    continue
                out.append(
                    (
                        _tokens(text),
                        {
                            "text": text,
                            "dialect": row.get("dialect") or "tunisian",
                            "tier": "dialect_hint",
                            "source": row.get("source") or "ArBanking77-Tunisian",
                        },
                    )
                )
    except OSError:
        return []
    return out


def suggest_for_text(text: str, *, limit: int = 3) -> list[dict]:
    """Return similar Hassaniya rewrites for a source prompt (suggestion-only)."""
    q = _tokens(text)
    if not q:
        return []
    scored: list[tuple[float, dict]] = []
    for toks, row in _suggest_index():
        if not toks:
            continue
        overlap = len(q & toks)
        if overlap <= 0:
            continue
        union = len(q | toks) or 1
        score = overlap / union
        if row.get("tier") == "gold":
            score += 0.15
        scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    out: list[dict] = []
    for score, row in scored:
        hs = row["hassaniya"]
        if hs in seen:
            continue
        seen.add(hs)
        out.append({**row, "score": round(score, 3)})
        if len(out) >= limit:
            break
    return out


def dialect_hints_for_text(text: str, *, limit: int = 2) -> list[dict]:
    """Tunisian/etc. banking lines — scaffolding only, never auto-train."""
    q = _tokens(text)
    if not q:
        return []
    scored: list[tuple[float, dict]] = []
    for toks, row in _dialect_index():
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
        out.append({**row, "score": round(score, 3), "flag": "dialect_hint"})
        if len(out) >= limit:
            break
    return out


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


def source_word_suggestions(text: str, *, limit: int = 16) -> list[dict]:
    """Hassaniya chips for the current source: full lines + words from best matches."""
    payload = build_draft(text)
    out: list[dict] = []
    seen: set[str] = set()

    def add(phrase: str, *, kind: str, tier: str = "suggest") -> None:
        p = (phrase or "").strip()
        if len(p) < 2 or p in seen:
            return
        seen.add(p)
        out.append({"phrase": p, "kind": kind, "tier": tier})

    draft = payload.get("draft") or {}
    if isinstance(draft, dict) and draft.get("text"):
        add(str(draft["text"]), kind="line", tier=str(draft.get("source") or "draft"))

    for it in payload.get("items") or []:
        add(str(it.get("hassaniya") or ""), kind="line", tier=str(it.get("tier") or "gold"))
        # Also surface tokens from that Hassaniya line for partial insert
        for tok in re.findall(r"[\u0600-\u06FF]{3,}", str(it.get("hassaniya") or "")):
            add(tok, kind="word", tier="from_match")

    for t in payload.get("templates") or []:
        pat = str(t.get("pattern") or "").replace(SLOT_MARK, "").strip()
        add(pat, kind="template", tier="template")

    for d in payload.get("dialectHints") or []:
        add(str(d.get("text") or ""), kind="dialect", tier="dialect_hint")

    # Global gold chips as extra completion stems
    for c in (load_chips().get("chips") or [])[:24]:
        if str(c.get("tier") or "") == "gold":
            add(str(c.get("phrase") or ""), kind="chip", tier="gold")

    return out[:limit]
