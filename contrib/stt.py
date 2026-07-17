"""Whisper STT assist — draft text only; never auto-approve."""

from __future__ import annotations

from pathlib import Path

import httpx

from api.config import Settings


async def transcribe_audio(path: Path, settings: Settings, *, language_hint: str | None = None) -> str:
    """Call OpenAI Whisper API (model whisper-1 ≈ large-v2/v3 family on API)."""
    api_key = settings.openai_api_key or settings.whisper_api_key
    if not api_key:
        raise RuntimeError(
            "STT is not configured. Set LEBNE_OPENAI_API_KEY (or LEBNE_WHISPER_API_KEY)."
        )

    lang_map = {"ar": "ar", "fr": "fr", "en": "en", "hassaniya": "ar"}
    language = lang_map.get((language_hint or "").lower())

    url = settings.whisper_api_base.rstrip("/") + "/audio/transcriptions"
    data: dict[str, str] = {"model": settings.whisper_model}
    if language:
        data["language"] = language

    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=120.0) as client:
        with path.open("rb") as fh:
            files = {"file": (path.name, fh, "application/octet-stream")}
            resp = await client.post(url, headers=headers, data=data, files=files)
        resp.raise_for_status()
        payload = resp.json()
    text = (payload.get("text") or "").strip()
    if not text:
        raise RuntimeError("Whisper returned empty transcript")
    return text
