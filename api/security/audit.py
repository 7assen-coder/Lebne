"""Append-only audit trail for sensitive actions."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from api.config import Settings, get_settings
from api.logging_utils import get_logger, redact

log = get_logger("audit")


@dataclass
class AuditEvent:
    ts: float
    user_id: str
    session_id: str | None
    action: str
    outcome: str
    detail: dict[str, Any]
    principal_roles: list[str]


class AuditLogger:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path("eval/results/audit.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        user_id: str,
        action: str,
        outcome: str,
        session_id: str | None = None,
        detail: dict[str, Any] | None = None,
        principal_roles: list[str] | None = None,
        settings: Settings | None = None,
    ) -> AuditEvent:
        settings = settings or get_settings()
        safe_detail = detail or {}
        if settings.redact_pii_in_logs:
            safe_detail = {
                k: redact(str(v)) if isinstance(v, str) else v for k, v in safe_detail.items()
            }
        event = AuditEvent(
            ts=time.time(),
            user_id=user_id,
            session_id=session_id,
            action=action,
            outcome=outcome,
            detail=safe_detail,
            principal_roles=principal_roles or [],
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        log.info("audit", **asdict(event))
        return event


audit_logger = AuditLogger()
