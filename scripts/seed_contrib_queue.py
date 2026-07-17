#!/usr/bin/env python3
"""Load imported_banking.jsonl into contrib prompt_items (read-only seed)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import func, select

from api.config import get_settings
from contrib.db import init_contrib_db, reset_contrib_engine, session_factory
from contrib.models import PromptItem

DEFAULT_SRC = Path("data/datasets/imported_banking.jsonl")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed contrib queue from imported_banking.jsonl")
    parser.add_argument("--source", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--limit", type=int, default=None, help="Optional cap for smoke runs")
    parser.add_argument("--reset-db-cache", action="store_true")
    args = parser.parse_args()

    if not args.source.exists():
        raise SystemExit(f"Missing source: {args.source}")

    get_settings.cache_clear()
    if args.reset_db_cache:
        reset_contrib_engine()
    init_contrib_db()
    factory = session_factory()

    inserted = 0
    skipped = 0
    with factory() as db:
        existing = {
            r for r in db.scalars(select(PromptItem.import_id)).all()
        }
        with args.source.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if args.limit is not None and inserted >= args.limit:
                    break
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                import_id = str(row.get("id") or f"line-{i}")
                if import_id in existing:
                    skipped += 1
                    continue
                messages = row.get("messages") or []
                user = next((m.get("content") for m in messages if m.get("role") == "user"), None)
                if not user:
                    skipped += 1
                    continue
                meta = row.get("meta") or {}
                assistant = next(
                    (m.get("content") for m in messages if m.get("role") == "assistant"),
                    None,
                )
                db.add(
                    PromptItem(
                        import_id=import_id,
                        source_text=str(user).strip(),
                        assistant_text=(str(assistant).strip() if assistant else None),
                        source_locale=str(row.get("locale") or "en"),
                        intent=str(row.get("intent") or "faq"),
                        source_label=(meta.get("source_label") or meta.get("source")),
                    )
                )
                existing.add(import_id)
                inserted += 1
                if inserted % 2000 == 0:
                    db.commit()
                    print(f"  … inserted {inserted}")
        db.commit()
        total = db.scalar(select(func.count()).select_from(PromptItem)) or 0

    print(f"inserted={inserted} skipped={skipped} total_prompts={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
