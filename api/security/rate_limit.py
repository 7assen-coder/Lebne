"""Simple fixed-window rate limiter (Redis when available)."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from api.config import Settings, get_settings


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._redis = None

    def _redis_client(self, settings: Settings):
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

    def check(self, key: str, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        if not settings.rate_limit_enabled:
            return
        limit = settings.rate_limit_requests
        window = settings.rate_limit_window_seconds
        r = self._redis_client(settings)
        if r is not None:
            rk = f"lebne:rl:{key}"
            count = r.incr(rk)
            if count == 1:
                r.expire(rk, window)
            if count > limit:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
            return

        now = time.time()
        bucket = self._hits[key]
        self._hits[key] = [t for t in bucket if now - t < window]
        if len(self._hits[key]) >= limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
        self._hits[key].append(now)


rate_limiter = RateLimiter()


async def enforce_rate_limit(request: Request, user_id: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    ip = request.client.host if request.client else "unknown"
    rate_limiter.check(f"{user_id}:{ip}", settings)
