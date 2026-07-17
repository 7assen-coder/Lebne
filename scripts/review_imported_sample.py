#!/usr/bin/env python3
"""Mark a deterministic sample of imported rows as reviewed=true after QA.

Default: up to 50 rows per locale that look safe (faq / account_action / clarify).
Rewrites the JSONL in place (or --out).
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("data/datasets/imported_banking.jsonl"),
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--per-locale", type=int, default=50)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    rows: list[dict] = []
    with args.path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    by_locale: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        if row.get("intent") in {"faq", "account_action", "clarify"}:
            by_locale[row.get("locale", "?")].append(i)

    rng = random.Random(args.seed)
    approved = 0
    for locale, indices in sorted(by_locale.items()):
        pick = list(indices)
        rng.shuffle(pick)
        for idx in pick[: args.per_locale]:
            rows[idx]["reviewed"] = True
            approved += 1
        print(f"locale={locale} candidates={len(indices)} approved={min(len(indices), args.per_locale)}")

    out = args.out or args.path
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    reviewed = sum(1 for r in rows if r.get("reviewed"))
    print(f"reviewed_total={reviewed} newly_marked≈{approved} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
