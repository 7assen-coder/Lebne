"""Logging helpers with optional PII redaction."""

from __future__ import annotations

import re

import structlog

from api.config import get_settings

PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{7,}\d")
CARD_RE = re.compile(r"\b\d{12,19}\b")
# Mauritanian NNI-style 10-digit national id (heuristic).
NNI_RE = re.compile(r"\b\d{10}\b")
EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
MRU_IBANISH_RE = re.compile(r"\bMR\d{2}[A-Z0-9]{10,30}\b", re.I)
JWT_RE = re.compile(r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+")


def redact(text: str) -> str:
    if not get_settings().redact_pii_in_logs:
        return text
    text = JWT_RE.sub("[REDACTED_TOKEN]", text)
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = MRU_IBANISH_RE.sub("[REDACTED_IBAN]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = CARD_RE.sub("[REDACTED_NUMBER]", text)
    text = NNI_RE.sub("[REDACTED_NNI]", text)
    return text


def get_logger(name: str = "lebne"):
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )
    return structlog.get_logger(name)
