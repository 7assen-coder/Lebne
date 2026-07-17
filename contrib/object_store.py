"""Durable audio object storage — Cloudflare R2 (S3) with Neon payload fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import quote

from api.config import Settings, get_settings

log = logging.getLogger("lebne.object_store")


@dataclass
class StoredObject:
    key: str
    content_type: str
    byte_size: int


class ObjectStoreError(RuntimeError):
    pass


class ObjectStore:
    """Abstract put/get/head/presign for audio assets."""

    backend: str  # "r2" | "neon"

    def configured(self) -> bool:
        return True

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        raise NotImplementedError

    def get(self, key: str) -> tuple[bytes, str] | None:
        raise NotImplementedError

    def head(self, key: str) -> StoredObject | None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def presign_put(self, key: str, content_type: str, expires_in: int = 900) -> dict[str, Any]:
        """Return { url, headers, method } for browser PUT. Neon backend returns empty (use multipart)."""
        raise NotImplementedError

    def health(self) -> dict[str, Any]:
        return {"backend": self.backend, "ok": True}


class R2ObjectStore(ObjectStore):
    backend = "r2"

    def __init__(self, settings: Settings) -> None:
        import boto3
        from botocore.config import Config

        if not (
            settings.r2_account_id
            and settings.r2_access_key_id
            and settings.r2_secret_access_key
            and settings.r2_bucket
        ):
            raise ObjectStoreError("R2 credentials incomplete")
        endpoint = (settings.r2_endpoint or "").strip() or (
            f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
        )
        self.bucket = settings.r2_bucket
        self.endpoint = endpoint.rstrip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return StoredObject(key=key, content_type=content_type, byte_size=len(data))

    def get(self, key: str) -> tuple[bytes, str] | None:
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=key)
        except Exception:  # noqa: BLE001
            return None
        body = obj["Body"].read()
        ctype = obj.get("ContentType") or "application/octet-stream"
        return body, ctype

    def head(self, key: str) -> StoredObject | None:
        try:
            obj = self._client.head_object(Bucket=self.bucket, Key=key)
        except Exception:  # noqa: BLE001
            return None
        return StoredObject(
            key=key,
            content_type=obj.get("ContentType") or "application/octet-stream",
            byte_size=int(obj.get("ContentLength") or 0),
        )

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # noqa: BLE001
            log.warning("r2_delete_failed key=%s err=%s", key, exc)

    def presign_put(self, key: str, content_type: str, expires_in: int = 900) -> dict[str, Any]:
        url = self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        return {
            "method": "PUT",
            "url": url,
            "headers": {"Content-Type": content_type},
            "expiresIn": expires_in,
        }

    def health(self) -> dict[str, Any]:
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return {"backend": "r2", "ok": True, "bucket": self.bucket}
        except Exception as exc:  # noqa: BLE001
            return {"backend": "r2", "ok": False, "error": str(exc)[:200]}


class NeonObjectStore(ObjectStore):
    """Dev/fallback: bytes in Postgres `contrib_audio_payloads` keyed by object_key."""

    backend = "neon"

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        from contrib.db import session_factory
        from contrib.models import AudioPayload

        factory = session_factory()
        db = factory()
        try:
            row = db.get(AudioPayload, key)
            if row:
                row.data = data
                row.content_type = content_type
                row.byte_size = len(data)
            else:
                db.add(
                    AudioPayload(
                        object_key=key,
                        data=data,
                        content_type=content_type,
                        byte_size=len(data),
                    )
                )
            db.commit()
        finally:
            db.close()
        return StoredObject(key=key, content_type=content_type, byte_size=len(data))

    def get(self, key: str) -> tuple[bytes, str] | None:
        from contrib.db import session_factory
        from contrib.models import AudioPayload

        factory = session_factory()
        db = factory()
        try:
            row = db.get(AudioPayload, key)
            if not row or not row.data:
                return None
            return bytes(row.data), row.content_type or "application/octet-stream"
        finally:
            db.close()

    def head(self, key: str) -> StoredObject | None:
        from contrib.db import session_factory
        from contrib.models import AudioPayload

        factory = session_factory()
        db = factory()
        try:
            row = db.get(AudioPayload, key)
            if not row:
                return None
            return StoredObject(
                key=key,
                content_type=row.content_type or "application/octet-stream",
                byte_size=int(row.byte_size or len(row.data or b"")),
            )
        finally:
            db.close()

    def delete(self, key: str) -> None:
        from contrib.db import session_factory
        from contrib.models import AudioPayload

        factory = session_factory()
        db = factory()
        try:
            row = db.get(AudioPayload, key)
            if row:
                db.delete(row)
                db.commit()
        finally:
            db.close()

    def presign_put(self, key: str, content_type: str, expires_in: int = 900) -> dict[str, Any]:
        # Browser must use multipart POST /crowd/v1/audio instead.
        return {
            "method": "MULTIPART",
            "url": "",
            "headers": {"Content-Type": content_type},
            "expiresIn": expires_in,
            "useMultipart": True,
        }

    def health(self) -> dict[str, Any]:
        return {"backend": "neon", "ok": True}


def r2_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(
        s.r2_account_id
        and s.r2_access_key_id
        and s.r2_secret_access_key
        and s.r2_bucket
    )


@lru_cache
def get_object_store() -> ObjectStore:
    settings = get_settings()
    if r2_configured(settings):
        try:
            return R2ObjectStore(settings)
        except Exception as exc:  # noqa: BLE001
            log.error("r2_init_failed falling_back_to_neon err=%s", exc)
    return NeonObjectStore()


def reset_object_store() -> None:
    get_object_store.cache_clear()


def quote_object_key(key: str) -> str:
    return quote(key, safe="/")
