"""Audio asset lifecycle: create → store (R2/Neon) → ready → stream."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import get_settings
from contrib.crowd_auth import effective_role
from contrib.media_util import EXT_FOR_MIME, MAX_AUDIO_BYTES, mime_for_filename
from contrib.models import (
    AUDIO_STATUS_FAILED,
    AUDIO_STATUS_READY,
    AUDIO_STATUS_UPLOADING,
    ROLE_OWNER,
    ROLE_REVIEWER,
    AudioAsset,
    AudioBlob,
    CrowdUser,
    Submission,
)
from contrib.object_store import get_object_store


ALLOWED_MIME = {
    "audio/webm",
    "audio/wav",
    "audio/mpeg",
    "audio/ogg",
    "audio/mp4",
    "audio/x-m4a",
    "audio/aac",
    "video/webm",  # some browsers mislabel webm audio
}


def normalize_mime(raw: str | None) -> str:
    mime = (raw or "audio/webm").split(";")[0].strip().lower()
    if mime == "audio/x-m4a":
        return "audio/mp4"
    if mime == "video/webm":
        return "audio/webm"
    if mime not in ALLOWED_MIME and not mime.startswith("audio/"):
        return "audio/webm"
    return mime if mime in ALLOWED_MIME or mime.startswith("audio/") else "audio/webm"


def ext_for_mime(mime: str) -> str:
    return EXT_FOR_MIME.get(normalize_mime(mime), ".webm")


def asset_out(asset: AudioAsset) -> dict:
    return {
        "audioId": asset.id,
        "status": asset.status,
        "contentType": asset.content_type,
        "byteSize": asset.byte_size,
        "storageBackend": asset.storage_backend,
        "ready": asset.status == AUDIO_STATUS_READY,
    }


def create_uploading_asset(
    db: Session,
    user: CrowdUser,
    *,
    content_type: str,
    byte_size: int = 0,
) -> tuple[AudioAsset, dict]:
    """Create uploading row + return presign info for the client."""
    settings = get_settings()
    max_b = int(settings.audio_max_bytes or MAX_AUDIO_BYTES)
    if byte_size and byte_size > max_b:
        raise ValueError(f"Audio too large (max {max_b} bytes)")

    mime = normalize_mime(content_type)
    store = get_object_store()
    asset_id = str(uuid.uuid4())
    key = f"crowd/{user.id}/{asset_id}{ext_for_mime(mime)}"
    asset = AudioAsset(
        id=asset_id,
        object_key=key,
        content_type=mime,
        byte_size=byte_size or 0,
        storage_backend=store.backend,
        uploaded_by=user.id,
        status=AUDIO_STATUS_UPLOADING,
    )
    db.add(asset)
    db.flush()
    presign = store.presign_put(key, mime)
    return asset, {
        **asset_out(asset),
        "upload": presign,
        "maxBytes": max_b,
        "objectKey": key,
    }


def put_bytes_and_ready(
    db: Session,
    user: CrowdUser,
    data: bytes,
    content_type: str,
) -> AudioAsset:
    settings = get_settings()
    max_b = int(settings.audio_max_bytes or MAX_AUDIO_BYTES)
    if len(data) < 32:
        raise ValueError("Empty audio")
    if len(data) > max_b:
        raise ValueError(f"Audio too large (max {max_b} bytes)")

    mime = normalize_mime(content_type)
    store = get_object_store()
    asset_id = str(uuid.uuid4())
    key = f"crowd/{user.id}/{asset_id}{ext_for_mime(mime)}"
    stored = store.put(key, data, mime)
    now = datetime.now(timezone.utc)
    asset = AudioAsset(
        id=asset_id,
        object_key=key,
        content_type=mime,
        byte_size=stored.byte_size,
        sha256=hashlib.sha256(data).hexdigest(),
        storage_backend=store.backend,
        uploaded_by=user.id,
        status=AUDIO_STATUS_READY,
        ready_at=now,
    )
    db.add(asset)
    db.flush()
    return asset


def complete_asset(db: Session, user: CrowdUser, audio_id: str) -> AudioAsset:
    asset = db.get(AudioAsset, audio_id)
    if not asset or asset.uploaded_by != user.id:
        raise LookupError("Audio not found")
    if asset.status == AUDIO_STATUS_READY:
        return asset

    store = get_object_store()
    # Neon multipart path: client may have already uploaded via /audio; head checks payload/R2
    meta = store.head(asset.object_key)
    if not meta or meta.byte_size < 32:
        asset.status = AUDIO_STATUS_FAILED
        db.flush()
        raise ValueError("Upload missing — retry record")

    asset.byte_size = meta.byte_size
    asset.content_type = meta.content_type or asset.content_type
    asset.status = AUDIO_STATUS_READY
    asset.ready_at = datetime.now(timezone.utc)
    asset.storage_backend = store.backend
    db.flush()
    return asset


def load_ready_bytes(db: Session, audio_id: str) -> tuple[bytes, str] | None:
    asset = db.get(AudioAsset, audio_id)
    if not asset or asset.status != AUDIO_STATUS_READY:
        return None
    store = get_object_store()
    got = store.get(asset.object_key)
    if got:
        return got
    # Legacy blob fallback by basename of object key
    name = asset.object_key.rsplit("/", 1)[-1]
    blob = db.get(AudioBlob, name)
    if blob and blob.data:
        return bytes(blob.data), blob.content_type or asset.content_type
    return None


def can_access_audio(db: Session, user: CrowdUser, audio_id: str) -> bool:
    """Uploader, reviewer/owner, or user linked via submission may stream."""
    asset = db.get(AudioAsset, audio_id)
    if not asset or asset.status != AUDIO_STATUS_READY:
        return False
    if asset.uploaded_by == user.id:
        return True
    role = effective_role(user)
    if role in (ROLE_OWNER, ROLE_REVIEWER):
        return True
    if asset.submission_id:
        sub = db.get(Submission, asset.submission_id)
        if sub and sub.user_id == user.id:
            return True
    # Also allow if any submission references this audio_id and belongs to user
    linked = db.scalar(
        select(Submission.id).where(
            Submission.audio_id == audio_id,
            Submission.user_id == user.id,
        )
    )
    return linked is not None


def resolve_ready_audio_id(
    db: Session,
    audio_id: str | None,
    *,
    require_owner_id: int | None = None,
) -> str | None:
    if not audio_id:
        return None
    asset = db.get(AudioAsset, audio_id)
    if not asset or asset.status != AUDIO_STATUS_READY:
        return None
    if require_owner_id is not None and asset.uploaded_by not in (None, require_owner_id):
        return None
    return asset.id


def link_asset_to_submission(db: Session, asset_id: str | None, submission: Submission) -> None:
    submission.audio_id = asset_id
    if asset_id:
        asset = db.get(AudioAsset, asset_id)
        if asset:
            asset.submission_id = submission.id
            # Keep legacy path empty for new assets
            submission.audio_path = None
    else:
        submission.audio_path = None


def playable_audio_id_for_submission(db: Session, sub: Submission) -> str | None:
    if not sub.audio_id:
        return None
    asset = db.get(AudioAsset, sub.audio_id)
    if not asset or asset.status != AUDIO_STATUS_READY:
        return None
    store = get_object_store()
    if store.head(asset.object_key) is not None:
        return asset.id
    return None


def migrate_legacy_blob_to_asset(
    db: Session,
    name: str,
    data: bytes,
    content_type: str,
    user_id: int | None,
) -> AudioAsset:
    """One-shot helper: legacy AudioBlob → durable asset."""
    store = get_object_store()
    asset_id = str(uuid.uuid4())
    mime = normalize_mime(content_type or mime_for_filename(name))
    key = f"crowd/legacy/{asset_id}{ext_for_mime(mime)}"
    store.put(key, data, mime)
    asset = AudioAsset(
        id=asset_id,
        object_key=key,
        content_type=mime,
        byte_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_backend=store.backend,
        uploaded_by=user_id,
        status=AUDIO_STATUS_READY,
        ready_at=datetime.now(timezone.utc),
    )
    db.add(asset)
    db.flush()
    return asset
