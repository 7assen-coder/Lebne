#!/usr/bin/env python3
"""Validate training JSONL: dedupe, reviewed flag, split quotas."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


REQUIRED_KEYS = {"id", "messages", "intent", "locale", "reviewed", "split"}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSONL at line {i}: {exc}") from exc
    return rows


def content_hash(row: dict) -> str:
    payload = json.dumps(row.get("messages"), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Lebne training dataset")
    parser.add_argument("dataset", type=Path)
    parser.add_argument(
        "--require-reviewed",
        action="store_true",
        help="Fail if any row has reviewed=false (use before fine-tune)",
    )
    args = parser.parse_args()

    rows = load_jsonl(args.dataset)
    missing = [r.get("id", "?") for r in rows if not REQUIRED_KEYS.issubset(r)]
    if missing:
        raise SystemExit(f"Missing required keys for ids: {missing[:10]}")

    if args.require_reviewed:
        unreviewed = [r["id"] for r in rows if not r.get("reviewed")]
        if unreviewed:
            raise SystemExit(f"{len(unreviewed)} rows not reviewed (e.g. {unreviewed[:5]})")

    hashes = [content_hash(r) for r in rows]
    dupes = len(hashes) - len(set(hashes))
    splits = Counter(r["split"] for r in rows)
    intents = Counter(r["intent"] for r in rows)

    print(f"rows={len(rows)} duplicates={dupes}")
    print(f"splits={dict(splits)}")
    print(f"intents={dict(intents)}")
    if dupes:
        raise SystemExit("Deduplicate before training")
    print("OK")


if __name__ == "__main__":
    main()
