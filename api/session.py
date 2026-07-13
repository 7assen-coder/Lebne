"""Session memory — Redis for production, in-memory fallback for local/dev."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from api.config import Settings, get_settings
from api.schemas import ChatMessage


@dataclass
class SessionState:
    user_id: str
    session_id: str
    messages: list[ChatMessage] = field(default_factory=list)
    summary: str | None = None


class SessionStore:
    """Isolation rule: every read/write is keyed by (user_id, session_id)."""

    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], SessionState] = {}
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

    def _key(self, user_id: str, session_id: str) -> str:
        return f"lebne:session:{user_id}:{session_id}"

    def get_or_create(self, user_id: str, session_id: str, settings: Settings | None = None) -> SessionState:
        settings = settings or get_settings()
        r = self._redis_client(settings)
        if r is not None:
            raw = r.get(self._key(user_id, session_id))
            if raw:
                data = json.loads(raw)
                if data.get("user_id") != user_id:
                    raise PermissionError("Session user mismatch")
                return SessionState(
                    user_id=user_id,
                    session_id=session_id,
                    messages=[ChatMessage(**m) for m in data.get("messages", [])],
                    summary=data.get("summary"),
                )
            state = SessionState(user_id=user_id, session_id=session_id)
            self._save_redis(state, settings)
            return state

        key = (user_id, session_id)
        if key not in self._sessions:
            self._sessions[key] = SessionState(user_id=user_id, session_id=session_id)
        return self._sessions[key]

    def _save_redis(self, state: SessionState, settings: Settings) -> None:
        r = self._redis_client(settings)
        if r is None:
            return
        payload = {
            "user_id": state.user_id,
            "session_id": state.session_id,
            "messages": [m.model_dump() for m in state.messages],
            "summary": state.summary,
        }
        r.set(
            self._key(state.user_id, state.session_id),
            json.dumps(payload, ensure_ascii=False),
            ex=settings.session_ttl_seconds,
        )

    def append(
        self,
        user_id: str,
        session_id: str,
        message: ChatMessage,
        settings: Settings | None = None,
    ) -> SessionState:
        settings = settings or get_settings()
        state = self.get_or_create(user_id, session_id, settings)
        if state.user_id != user_id:
            raise PermissionError("Session user mismatch")
        state.messages.append(message)
        if self._redis_client(settings) is not None:
            self._save_redis(state, settings)
        else:
            self._sessions[(user_id, session_id)] = state
        return state


session_store = SessionStore()
