#!/usr/bin/env python3
"""Rebuild lebne_mru_{en,fr,ar,hassaniya}.jsonl from approved submissions."""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from api.config import get_settings
from contrib.db import init_contrib_db, session_factory
from contrib.export_util import LOCALES, rewrite_locale_files, rows_from_approved_submissions
from contrib.models import Submission


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("data/datasets"))
    parser.add_argument(
        "--fill-missing-views",
        action="store_true",
        help="MT-fill missing EN/FR/AR source views (same as web download)",
    )
    args = parser.parse_args()

    get_settings.cache_clear()
    init_contrib_db()
    factory = session_factory()

    with factory() as db:
        rows = db.scalars(
            select(Submission)
            .options(joinedload(Submission.prompt))
            .where(Submission.status == "approved")
            .order_by(Submission.id.asc())
        ).unique().all()
        by_locale = rows_from_approved_submissions(
            list(rows),
            db=db,
            fill_missing_views=args.fill_missing_views,
        )

    counts = rewrite_locale_files(by_locale, args.out_dir)
    print("Rewrote locale files:")
    for loc, n in counts.items():
        print(f"  lebne_mru_{loc}.jsonl → {n} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
