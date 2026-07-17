#!/usr/bin/env python3
"""One-shot: legacy contrib_audio_blobs → durable AudioAsset (R2 or Neon payload).

Also clears unrecoverable submission.audio_path when no bytes remain.
Usage (API env loaded):
  python scripts/migrate_audio_blobs_to_assets.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from contrib.audio_service import migrate_legacy_blob_to_asset  # noqa: E402
from contrib.db import init_contrib_db, session_factory  # noqa: E402
from contrib.media_util import audio_basename  # noqa: E402
from contrib.models import AudioBlob, Submission  # noqa: E402
from contrib.object_store import get_object_store, reset_object_store  # noqa: E402


def main() -> int:
    init_contrib_db()
    reset_object_store()
    store = get_object_store()
    print(f"object_store={store.backend} health={store.health()}")

    factory = session_factory()
    db = factory()
    migrated = 0
    linked = 0
    cleared = 0
    try:
        blobs = db.scalars(select(AudioBlob)).all()
        name_to_asset: dict[str, str] = {}
        for blob in blobs:
            if not blob.data:
                continue
            asset = migrate_legacy_blob_to_asset(
                db,
                blob.name,
                bytes(blob.data),
                blob.content_type or "audio/webm",
                user_id=None,
            )
            name_to_asset[blob.name] = asset.id
            migrated += 1
        db.commit()

        try:
            subs = db.scalars(select(Submission).where(Submission.audio_path.is_not(None))).all()
        except Exception as exc:  # noqa: BLE001
            print(f"skip_submission_link reason={exc}")
            subs = []
        for sub in subs:
            if sub.audio_id:
                continue
            name = audio_basename(sub.audio_path)
            if name and name in name_to_asset:
                sub.audio_id = name_to_asset[name]
                sub.audio_path = None
                linked += 1
            else:
                # No recoverable bytes — stop advertising a dead path
                sub.audio_path = None
                cleared += 1
        if subs:
            db.commit()
    finally:
        db.close()

    print(f"migrated_blobs={migrated} linked_submissions={linked} cleared_dead_paths={cleared}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
