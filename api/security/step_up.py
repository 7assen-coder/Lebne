"""Cryptographic confirmation + 2FA step-up tokens (single-use)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import HTTPException, status

from api.config import Settings, get_settings
from api.schemas import AccountActionType


@dataclass
class StepUpChallenge:
    confirmation_token: str
    two_fa_required: bool
    two_fa_challenge_id: str | None = None
    expires_in: int = 300


class OneTimeStore:
    """Tracks consumed jti values. Redis-backed when configured."""

    def __init__(self) -> None:
        self._memory: dict[str, float] = {}
        self._redis = None

    def _get_redis(self, settings: Settings):
        if settings.session_backend != "redis" or not settings.redis_url:
            return None
        if self._redis is None:
            try:
                import redis

                self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = False
        return self._redis if self._redis is not False else None

    def consume(self, jti: str, ttl: int, settings: Settings) -> bool:
        """Return True if first use; False if already consumed."""
        r = self._get_redis(settings)
        key = f"lebne:stepup:used:{jti}"
        if r is not None:
            ok = r.set(name=key, value="1", nx=True, ex=ttl)
            return bool(ok)
        now = time.time()
        # purge expired
        expired = [k for k, exp in self._memory.items() if exp < now]
        for k in expired:
            del self._memory[k]
        if jti in self._memory:
            return False
        self._memory[jti] = now + ttl
        return True


_one_time = OneTimeStore()
_pending_2fa: dict[str, dict[str, Any]] = {}


def _sign_code(challenge_id: str, settings: Settings) -> str:
    """Dev-friendly deterministic 6-digit code from challenge (replace with SMS/TOTP)."""
    digest = hmac.new(
        settings.jwt_secret.encode(),
        challenge_id.encode(),
        hashlib.sha256,
    ).hexdigest()
    return str(int(digest[:8], 16) % 1_000_000).zfill(6)


def issue_confirmation(
    *,
    user_id: str,
    action: AccountActionType,
    session_id: str,
    settings: Settings | None = None,
) -> StepUpChallenge:
    settings = settings or get_settings()
    now = int(time.time())
    jti = secrets.token_urlsafe(16)
    two_fa_required = action in {
        AccountActionType.CHANGE_PASSWORD,
        AccountActionType.CHANGE_PHONE,
    }
    payload = {
        "sub": user_id,
        "action": action.value,
        "session_id": session_id,
        "token_use": "confirmation",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + settings.step_up_token_ttl_seconds,
        "jti": jti,
        "two_fa_required": two_fa_required,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    challenge_id = None
    if two_fa_required:
        challenge_id = secrets.token_urlsafe(12)
        code = _sign_code(challenge_id, settings)
        _pending_2fa[challenge_id] = {
            "user_id": user_id,
            "action": action.value,
            "code_hash": hashlib.sha256(code.encode()).hexdigest(),
            "exp": now + settings.step_up_token_ttl_seconds,
            "consumed": False,
        }
    return StepUpChallenge(
        confirmation_token=token,
        two_fa_required=two_fa_required,
        two_fa_challenge_id=challenge_id,
        expires_in=settings.step_up_token_ttl_seconds,
    )


def verify_confirmation_token(
    token: str,
    *,
    user_id: str,
    action: AccountActionType,
    session_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid confirmation token") from exc

    if payload.get("token_use") != "confirmation":
        raise HTTPException(status_code=403, detail="Wrong token type")
    if payload.get("sub") != user_id:
        raise HTTPException(status_code=403, detail="Confirmation token user mismatch")
    if payload.get("action") != action.value:
        raise HTTPException(status_code=403, detail="Confirmation token action mismatch")
    if payload.get("session_id") != session_id:
        raise HTTPException(status_code=403, detail="Confirmation token session mismatch")

    jti = payload.get("jti")
    if not jti or not _one_time.consume(jti, settings.step_up_token_ttl_seconds, settings):
        raise HTTPException(status_code=403, detail="Confirmation token already used or missing jti")
    return payload


def verify_two_fa(
    *,
    challenge_id: str,
    code: str,
    user_id: str,
    action: AccountActionType,
    settings: Settings | None = None,
) -> str:
    """Verify 2FA code and return a short-lived two_fa_token bound to the action."""
    settings = settings or get_settings()
    pending = _pending_2fa.get(challenge_id)
    if not pending:
        raise HTTPException(status_code=403, detail="Unknown 2FA challenge")
    if pending["consumed"]:
        raise HTTPException(status_code=403, detail="2FA challenge already used")
    if pending["exp"] < int(time.time()):
        raise HTTPException(status_code=403, detail="2FA challenge expired")
    if pending["user_id"] != user_id or pending["action"] != action.value:
        raise HTTPException(status_code=403, detail="2FA challenge mismatch")
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    if not hmac.compare_digest(code_hash, pending["code_hash"]):
        raise HTTPException(status_code=403, detail="Invalid 2FA code")
    pending["consumed"] = True

    now = int(time.time())
    jti = secrets.token_urlsafe(12)
    token = jwt.encode(
        {
            "sub": user_id,
            "action": action.value,
            "token_use": "two_fa",
            "challenge_id": challenge_id,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "exp": now + settings.step_up_token_ttl_seconds,
            "jti": jti,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token


def verify_two_fa_token(
    token: str,
    *,
    user_id: str,
    action: AccountActionType,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=403, detail="Invalid 2FA token") from exc
    if payload.get("token_use") != "two_fa":
        raise HTTPException(status_code=403, detail="Wrong token type")
    if payload.get("sub") != user_id or payload.get("action") != action.value:
        raise HTTPException(status_code=403, detail="2FA token mismatch")
    jti = payload.get("jti")
    if not jti or not _one_time.consume(f"2fa:{jti}", settings.step_up_token_ttl_seconds, settings):
        raise HTTPException(status_code=403, detail="2FA token already used")


def peek_dev_2fa_code(challenge_id: str, settings: Settings | None = None) -> str | None:
    """Development only — never expose in production APIs."""
    settings = settings or get_settings()
    if settings.env == "production":
        return None
    if challenge_id not in _pending_2fa:
        return None
    return _sign_code(challenge_id, settings)
