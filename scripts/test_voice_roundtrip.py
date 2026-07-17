#!/usr/bin/env python3
"""Pre-deploy voice round-trip: store → load → access control."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Isolated SQLite for the smoke test
fd, db_path = tempfile.mkstemp(suffix=".sqlite3")
os.close(fd)
os.environ["LEBNE_CONTRIB_DATABASE_URL"] = f"sqlite:///{db_path}"
os.environ.pop("DATABASE_URL", None)
# Force Neon-style payload store (no R2 required)
for key in (
    "LEBNE_R2_ACCOUNT_ID",
    "LEBNE_R2_ACCESS_KEY_ID",
    "LEBNE_R2_SECRET_ACCESS_KEY",
    "LEBNE_R2_BUCKET",
):
    os.environ.pop(key, None)

from api.config import get_settings

get_settings.cache_clear()

from sqlalchemy.orm import sessionmaker

from contrib.audio_service import (
    can_access_audio,
    load_ready_bytes,
    playable_audio_id_for_submission,
    put_bytes_and_ready,
)
from contrib.db import get_contrib_engine, init_contrib_db, reset_contrib_engine
from contrib.models import ROLE_OWNER, ROLE_REVIEWER, CrowdUser, PromptItem, Submission
from contrib.object_store import get_object_store, reset_object_store


def main() -> int:
    reset_contrib_engine()
    try:
        reset_object_store()
    except Exception:
        pass
    init_contrib_db()
    store = get_object_store()
    print(f"object_store_ready backend={store.backend}")

    SessionLocal = sessionmaker(bind=get_contrib_engine(), autoflush=False, autocommit=False)
    db = SessionLocal()
    try:
        owner = CrowdUser(
            email="owner@test.local",
            name="Owner",
            password_hash="x",
            role=ROLE_OWNER,
            is_admin=True,
        )
        uploader = CrowdUser(
            email="contrib@test.local",
            name="Contributor",
            password_hash="x",
            role="contributor",
            is_admin=False,
        )
        stranger = CrowdUser(
            email="other@test.local",
            name="Other",
            password_hash="x",
            role="contributor",
            is_admin=False,
        )
        reviewer = CrowdUser(
            email="review@test.local",
            name="Reviewer",
            password_hash="x",
            role=ROLE_REVIEWER,
            is_admin=False,
        )
        db.add_all([owner, uploader, stranger, reviewer])
        db.commit()
        for u in (owner, uploader, stranger, reviewer):
            db.refresh(u)

        fake = b"\x1aE\xdf\xa3" + b"\x00" * 200  # tiny webm-ish
        asset = put_bytes_and_ready(db, uploader, fake, "audio/webm")
        db.commit()
        print(f"uploaded audioId={asset.id} status={asset.status}")

        loaded = load_ready_bytes(db, asset.id)
        assert loaded is not None, "load_ready_bytes failed"
        data, mime = loaded
        assert data == fake, "bytes mismatch"
        assert "audio" in mime or mime == "video/webm", mime
        print(f"roundtrip_ok bytes={len(data)} mime={mime}")

        assert can_access_audio(db, uploader, asset.id), "uploader should access"
        assert can_access_audio(db, owner, asset.id), "owner should access"
        assert can_access_audio(db, reviewer, asset.id), "reviewer should access"
        assert not can_access_audio(db, stranger, asset.id), "stranger must be denied"
        print("idor_ok uploader/owner/reviewer allowed; stranger denied")

        # Oversize rejected
        try:
            put_bytes_and_ready(db, uploader, b"x" * (9_000_000), "audio/webm")
            print("FAIL: oversized upload accepted")
            return 1
        except ValueError:
            print("size_cap_ok")

        # Empty / tiny payload rejected
        try:
            put_bytes_and_ready(db, uploader, b"tiny", "audio/webm")
            print("FAIL: tiny upload accepted")
            return 1
        except ValueError:
            print("empty_reject_ok")

        # Linked submission is playable (admin Inbox/Approved path)
        prompt = PromptItem(
            import_id="test-voice-1",
            source_text="bonjour",
            source_locale="fr",
            intent="greet",
        )
        db.add(prompt)
        db.flush()
        sub = Submission(
            prompt_id=prompt.id,
            user_id=uploader.id,
            target_locale="hassaniya",
            text="[voice]",
            audio_id=asset.id,
            status="pending",
        )
        db.add(sub)
        db.commit()
        playable = playable_audio_id_for_submission(db, sub)
        assert playable == asset.id, "playable_audio_id_for_submission should return ready asset"
        print("playable_submission_ok")

        # STT-style durability: asset committed even if a later step "fails"
        asset2 = put_bytes_and_ready(db, uploader, fake + b"\x01", "audio/mp4")
        db.commit()
        assert load_ready_bytes(db, asset2.id) is not None
        print("stt_commit_survive_ok")

        print("VOICE_ROUNDTRIP_PASS")
        return 0
    finally:
        db.close()
        try:
            os.unlink(db_path)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
