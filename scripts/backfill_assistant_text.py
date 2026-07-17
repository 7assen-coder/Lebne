#!/usr/bin/env python3
"""Fill PromptItem.assistant_text from imported_banking.jsonl for existing rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from api.config import get_settings
from contrib.db import init_contrib_db, reset_contrib_engine, session_factory
from contrib.models import PromptItem

DEFAULT_SRC = Path("data/datasets/imported_banking.jsonl")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SRC)
    args = parser.parse_args()
    if not args.source.exists():
        raise SystemExit(f"Missing {args.source}")

    get_settings.cache_clear()
    reset_contrib_engine()
    init_contrib_db()
    factory = session_factory()

    by_id: dict[str, str] = {}
    with args.source.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            import_id = str(row.get("id") or f"line-{i}")
            messages = row.get("messages") or []
            assistant = next(
                (m.get("content") for m in messages if m.get("role") == "assistant"),
                None,
            )
            if assistant:
                by_id[import_id] = str(assistant).strip()

    updated = 0
    with factory() as db:
        for item in db.scalars(select(PromptItem)).yield_per(1000):
            text = by_id.get(item.import_id)
            if not text:
                continue
            if item.assistant_text == text:
                continue
            item.assistant_text = text
            updated += 1
            if updated % 2000 == 0:
                db.commit()
                print(f"  … updated {updated}")
        db.commit()
    print(f"updated={updated} mapped={len(by_id)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
