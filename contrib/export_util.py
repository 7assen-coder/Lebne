"""Append / rebuild approved submissions into locale JSONL files (training-safe)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from contrib.replies import assistant_reply

LOCALES = ("en", "fr", "ar", "hassaniya")
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
) -> dict:
    """Training row: source question → Hassaniya rewrite (no PII / audio paths).

    messages[0] user = original prompt (FR/AR/EN/…)
    messages[1] assistant = contributor Hassaniya (or explicit answer when set)
    """
    split = assign_split(f"{submission_id}:{locale}")
    source = (source_text or "").strip()
    hassaniya = (text or "").strip()
    faq_answer = (answer or "").strip()

    if source:
        user_content = source
        # Prefer explicit FAQ answer when reviewers filled it; else Hassaniya rewrite.
        assistant_content = faq_answer or hassaniya or assistant_reply(intent, locale)
    else:
        # Legacy fallback when prompt text is missing.
        user_content = hassaniya or "[empty]"
        assistant_content = faq_answer or assistant_reply(intent, locale)

    row = {
        "schema_version": SCHEMA_VERSION,
        "id": f"mru-{locale}-{submission_id:06d}",
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
    # Keep Hassaniya utterance even when assistant used FAQ answer instead.
    if hassaniya and hassaniya != assistant_content:
        row["hassaniya"] = hassaniya
    return row


def sanitize_training_row(row: dict) -> dict:
    """Drop PII / non-training fields; keep stable training schema."""
    out = {k: v for k, v in row.items() if k not in _PII_KEYS}
    if "schema_version" not in out:
        out["schema_version"] = SCHEMA_VERSION
    # Nested contributor object from older exports
    out.pop("contributor", None)
    return out


def append_approved_row(row: dict, out_dir: Path = DEFAULT_OUT_DIR) -> Path:
    path = locale_path(row["locale"], out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = sanitize_training_row(row)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(clean, ensure_ascii=False) + "\n")
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
) -> dict[str, list[dict]]:
    """Build training rows from approved Submission ORM objects (include answer_text)."""
    by_locale: dict[str, list[dict]] = {loc: [] for loc in LOCALES}
    for sub in submissions:
        prompt = getattr(sub, "prompt", None)
        loc = (getattr(sub, "target_locale", None) or "").strip()
        if not prompt or loc not in LOCALES:
            continue
        if locale and loc != locale:
            continue
        by_locale[loc].append(
            row_from_submission(
                submission_id=sub.id,
                intent=prompt.intent,
                locale=loc,
                text=sub.text,
                answer=getattr(sub, "answer_text", None),
                source_text=getattr(prompt, "source_text", None),
                source_locale=getattr(prompt, "source_locale", None),
                contributor_id=getattr(sub, "user_id", None),
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
