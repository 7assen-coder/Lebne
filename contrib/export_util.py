"""Append / rebuild approved submissions into locale JSONL files (training-safe)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from contrib.replies import assistant_reply

LOCALES = ("en", "fr", "ar", "hassaniya")
# Product / queue view languages — each becomes a training user turn when available.
SOURCE_VIEW_LOCALES = ("en", "fr", "ar")
DEFAULT_OUT_DIR = Path("data/datasets")
SCHEMA_VERSION = 2
# Never write these keys into training JSONL
_PII_KEYS = frozenset({"contributor", "email", "name", "audio_path", "phone"})


def locale_path(locale: str, out_dir: Path = DEFAULT_OUT_DIR) -> Path:
    return out_dir / f"lebne_mru_{locale}.jsonl"


def assign_split(key: str) -> str:
    digest = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 100
    if digest < 80:
        return "train"
    if digest < 90:
        return "val"
    return "test"


def _cached_view_text(hit: Any) -> str | None:
    if isinstance(hit, str) and hit.strip():
        return hit.strip()
    if isinstance(hit, dict):
        t = hit.get("text") or hit.get("question")
        if isinstance(t, str) and t.strip():
            return t.strip()
    return None


def _load_translations_cache(prompt: Any) -> dict[str, Any]:
    raw = getattr(prompt, "translations_json", None) if prompt is not None else None
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def collect_source_views(
    prompt: Any,
    *,
    db: Any | None = None,
    fill_missing: bool = False,
) -> dict[str, str]:
    """Resolve EN/FR/AR utterance texts for a prompt (source + cached MT; optional live fill).

    Returns only locales that have non-empty text. Does not invent empty keys.
    """
    out: dict[str, str] = {}
    if prompt is None:
        return out

    src_loc = (getattr(prompt, "source_locale", None) or "").lower().strip()
    src_text = (getattr(prompt, "source_text", None) or "").strip()
    if src_text:
        if src_loc in SOURCE_VIEW_LOCALES:
            out[src_loc] = src_text
        else:
            # Unknown source locale — still keep one training user turn.
            out[src_loc or "en"] = src_text

    cache = _load_translations_cache(prompt)
    for loc in SOURCE_VIEW_LOCALES:
        if loc in out:
            continue
        hit = _cached_view_text(cache.get(loc))
        if hit:
            out[loc] = hit

    if fill_missing and db is not None and prompt is not None:
        from contrib.translate_view import view_text

        for loc in SOURCE_VIEW_LOCALES:
            if loc in out and out[loc].strip():
                continue
            try:
                got = view_text(db, prompt, loc)
            except Exception:  # noqa: BLE001 — export must not fail on MT
                continue
            text = (got.get("text") or "").strip() if isinstance(got, dict) else ""
            if text:
                out[loc] = text

    return {k: v for k, v in out.items() if (v or "").strip()}


def _assistant_content(
    *,
    locale: str,
    intent: str,
    hassaniya: str,
    faq_answer: str,
    has_source: bool,
) -> str:
    if has_source:
        return faq_answer or hassaniya or assistant_reply(intent, locale)
    return faq_answer or assistant_reply(intent, locale)


def row_from_submission(
    *,
    submission_id: int,
    intent: str,
    locale: str,
    text: str,
    answer: str | None = None,
    source_text: str | None = None,
    source_locale: str | None = None,
    contributor_id: int | None = None,
    id_suffix: str | None = None,
) -> dict:
    """One training row: source question → Hassaniya rewrite (no PII / audio paths).

    messages[0] user = original prompt (FR/AR/EN/…)
    messages[1] assistant = contributor Hassaniya (or explicit answer when set)
    """
    split = assign_split(f"{submission_id}:{locale}")
    source = (source_text or "").strip()
    hassaniya = (text or "").strip()
    faq_answer = (answer or "").strip()

    if source:
        user_content = source
        assistant_content = _assistant_content(
            locale=locale,
            intent=intent,
            hassaniya=hassaniya,
            faq_answer=faq_answer,
            has_source=True,
        )
    else:
        user_content = hassaniya or "[empty]"
        assistant_content = _assistant_content(
            locale=locale,
            intent=intent,
            hassaniya=hassaniya,
            faq_answer=faq_answer,
            has_source=False,
        )

    suffix = f"-{id_suffix}" if id_suffix else ""
    row = {
        "schema_version": SCHEMA_VERSION,
        "id": f"mru-{locale}-{submission_id:06d}{suffix}",
        "intent": intent,
        "locale": locale,
        "reviewed": True,
        "split": split,
        "contributor_id": contributor_id,
        "messages": [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ],
    }
    if source_locale:
        row["source_locale"] = source_locale
    if hassaniya and hassaniya != assistant_content:
        row["hassaniya"] = hassaniya
    return row


def rows_from_submission(
    *,
    submission_id: int,
    intent: str,
    locale: str,
    text: str,
    answer: str | None = None,
    source_text: str | None = None,
    source_locale: str | None = None,
    contributor_id: int | None = None,
    source_views: dict[str, str] | None = None,
    prompt: Any | None = None,
    db: Any | None = None,
    fill_missing_views: bool = False,
) -> list[dict]:
    """Expand one submission into one training row per available EN/FR/AR source.

    Same Hassaniya (or FAQ answer) is the assistant for every source language so
    clients asking in any of those languages map to the same rewrite.
    """
    views = dict(source_views or {})
    if not views and prompt is not None:
        views = collect_source_views(prompt, db=db, fill_missing=fill_missing_views)
    if not views:
        src = (source_text or "").strip()
        src_loc = (source_locale or "").lower().strip() or None
        if src:
            views = {src_loc or "en": src}

    if not views:
        return [
            row_from_submission(
                submission_id=submission_id,
                intent=intent,
                locale=locale,
                text=text,
                answer=answer,
                source_text=None,
                source_locale=source_locale,
                contributor_id=contributor_id,
            )
        ]

    # Prefer stable order: en, fr, ar, then any extras.
    order = [loc for loc in SOURCE_VIEW_LOCALES if loc in views]
    order.extend(sorted(loc for loc in views if loc not in SOURCE_VIEW_LOCALES))

    rows: list[dict] = []
    for src_loc in order:
        src = (views.get(src_loc) or "").strip()
        if not src:
            continue
        # Always suffix with source locale so EN/FR/AR variants replace cleanly.
        rows.append(
            row_from_submission(
                submission_id=submission_id,
                intent=intent,
                locale=locale,
                text=text,
                answer=answer,
                source_text=src,
                source_locale=src_loc,
                contributor_id=contributor_id,
                id_suffix=src_loc,
            )
        )
    return rows or [
        row_from_submission(
            submission_id=submission_id,
            intent=intent,
            locale=locale,
            text=text,
            answer=answer,
            source_text=source_text,
            source_locale=source_locale,
            contributor_id=contributor_id,
        )
    ]


def sanitize_training_row(row: dict) -> dict:
    """Drop PII / non-training fields; keep stable training schema."""
    out = {k: v for k, v in row.items() if k not in _PII_KEYS}
    if "schema_version" not in out:
        out["schema_version"] = SCHEMA_VERSION
    out.pop("contributor", None)
    return out


def append_approved_row(row: dict, out_dir: Path = DEFAULT_OUT_DIR) -> Path:
    path = locale_path(row["locale"], out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = sanitize_training_row(row)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(clean, ensure_ascii=False) + "\n")
    return path


def append_approved_rows(rows: list[dict], out_dir: Path = DEFAULT_OUT_DIR) -> Path | None:
    path: Path | None = None
    for row in rows:
        path = append_approved_row(row, out_dir)
    return path


def upsert_approved_row(row: dict, out_dir: Path = DEFAULT_OUT_DIR) -> Path:
    """Replace an existing JSONL row with the same id, or append if missing."""
    path = locale_path(row["locale"], out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = sanitize_training_row(row)
    row_id = clean.get("id")
    lines: list[str] = []
    replaced = False
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row_id and existing.get("id") == row_id:
                lines.append(json.dumps(clean, ensure_ascii=False))
                replaced = True
            else:
                lines.append(json.dumps(sanitize_training_row(existing), ensure_ascii=False))
    if not replaced:
        lines.append(json.dumps(clean, ensure_ascii=False))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def replace_submission_export_rows(
    *,
    submission_id: int,
    locale: str,
    rows: list[dict],
    out_dir: Path = DEFAULT_OUT_DIR,
) -> Path:
    """Drop all prior lines for this submission id prefix, then write the new expanded set."""
    path = locale_path(locale, out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"mru-{locale}-{submission_id:06d}"
    kept: list[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            eid = str(existing.get("id") or "")
            if eid == prefix or eid.startswith(prefix + "-"):
                continue
            kept.append(json.dumps(sanitize_training_row(existing), ensure_ascii=False))
    for row in rows:
        kept.append(json.dumps(sanitize_training_row(row), ensure_ascii=False))
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return path


def count_nonempty_lines(path: Path) -> int:
    """Stream line count without loading the whole file into memory."""
    if not path.is_file():
        return 0
    n = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return n


def scrub_all_locale_files(out_dir: Path = DEFAULT_OUT_DIR, *, force: bool = False) -> dict[str, int]:
    """Rewrite all lebne_mru_*.jsonl without PII (idempotent).

    Uses a marker file so startup does not rewrite large JSONL on every boot.
    """
    counts: dict[str, int] = {}
    out_dir.mkdir(parents=True, exist_ok=True)
    marker = out_dir / ".scrubbed_training_v1"
    if marker.is_file() and not force:
        for locale in LOCALES:
            path = locale_path(locale, out_dir)
            counts[locale] = count_nonempty_lines(path) if path.is_file() else 0
        return counts
    for locale in LOCALES:
        path = locale_path(locale, out_dir)
        if not path.exists():
            counts[locale] = 0
            continue
        cleaned_lines: list[str] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cleaned_lines.append(json.dumps(sanitize_training_row(row), ensure_ascii=False))
        path.write_text("\n".join(cleaned_lines) + ("\n" if cleaned_lines else ""), encoding="utf-8")
        counts[locale] = len(cleaned_lines)
    marker.write_text("ok\n", encoding="utf-8")
    return counts


def rows_from_approved_submissions(
    submissions: list,
    *,
    locale: str | None = None,
    db: Any | None = None,
    fill_missing_views: bool = False,
) -> dict[str, list[dict]]:
    """Build training rows from approved Submission ORM objects (include answer_text).

    Expands each submission into EN/FR/AR → Hassaniya rows when those source texts exist.
    When ``fill_missing_views`` and ``db`` are set (download path), missing views are
    filled via cached/live MT so the file includes all three languages when possible.
    """
    by_locale: dict[str, list[dict]] = {loc: [] for loc in LOCALES}
    for sub in submissions:
        prompt = getattr(sub, "prompt", None)
        loc = (getattr(sub, "target_locale", None) or "").strip()
        if not prompt or loc not in LOCALES:
            continue
        if locale and loc != locale:
            continue
        by_locale[loc].extend(
            rows_from_submission(
                submission_id=sub.id,
                intent=prompt.intent,
                locale=loc,
                text=sub.text,
                answer=getattr(sub, "answer_text", None),
                source_text=getattr(prompt, "source_text", None),
                source_locale=getattr(prompt, "source_locale", None),
                contributor_id=getattr(sub, "user_id", None),
                prompt=prompt,
                db=db,
                fill_missing_views=fill_missing_views,
            )
        )
    return by_locale


def jsonl_bytes_for_locale(rows: list[dict]) -> bytes:
    """UTF-8 JSONL payload (one sanitized object per line)."""
    lines = [
        json.dumps(sanitize_training_row(row), ensure_ascii=False) for row in rows
    ]
    body = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    return body


def rewrite_locale_files(rows_by_locale: dict[str, list[dict]], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, int]:
    counts: dict[str, int] = {}
    out_dir.mkdir(parents=True, exist_ok=True)
    for locale in LOCALES:
        path = locale_path(locale, out_dir)
        rows = rows_by_locale.get(locale) or []
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(sanitize_training_row(row), ensure_ascii=False) + "\n")
        counts[locale] = len(rows)
    return counts
