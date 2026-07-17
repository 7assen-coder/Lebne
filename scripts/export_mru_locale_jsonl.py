#!/usr/bin/env python3
"""Rebuild lebne_mru_{en,fr,ar,hassaniya}.jsonl from approved submissions."""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from api.config import get_settings
from contrib.db import init_contrib_db, session_factory
from contrib.export_util import LOCALES, rewrite_locale_files, row_from_submission
from contrib.models import Submission


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("data/datasets"))
    args = parser.parse_args()

    get_settings.cache_clear()
    init_contrib_db()
    factory = session_factory()
    by_locale: dict[str, list[dict]] = {loc: [] for loc in LOCALES}

    with factory() as db:
        rows = db.scalars(
            select(Submission)
            .options(joinedload(Submission.prompt))
            .where(Submission.status == "approved")
            .order_by(Submission.id.asc())
        ).unique().all()
        for sub in rows:
            if not sub.prompt or sub.target_locale not in LOCALES:
                continue
            by_locale[sub.target_locale].append(
                row_from_submission(
                    submission_id=sub.id,
                    intent=sub.prompt.intent,
                    locale=sub.target_locale,
                    text=sub.text,
                )
            )

    counts = rewrite_locale_files(by_locale, args.out_dir)
    print("Rewrote locale files:")
    for loc, n in counts.items():
        print(f"  lebne_mru_{loc}.jsonl → {n} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
