"""Render the SAME source utterance in fr/ar/en — never swap rows, never surface AI replies.

Uses file text when source_locale matches the view; otherwise translates and caches.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from contrib.models import PromptItem

log = logging.getLogger("lebne.crowd.translate")

VIEW_LOCALES = ("en", "fr", "ar")
_LANGPAIR = {
    ("en", "fr"): "en|fr",
    ("en", "ar"): "en|ar",
    ("fr", "en"): "fr|en",
    ("fr", "ar"): "fr|ar",
    ("ar", "en"): "ar|en",
    ("ar", "fr"): "ar|fr",
}


def _load_cache(prompt: PromptItem) -> dict[str, Any]:
    if not prompt.translations_json:
        return {}
    try:
        data = json.loads(prompt.translations_json)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_cache(db: Session, prompt: PromptItem, cache: dict[str, Any]) -> None:
    prompt.translations_json = json.dumps(cache, ensure_ascii=False)
    db.add(prompt)
    db.commit()


def _cached_text(hit: Any) -> str | None:
    if isinstance(hit, str) and hit.strip():
        return hit.strip()
    if isinstance(hit, dict):
        # New shape: {"text": "..."}; ignore legacy AI answer fields
        t = hit.get("text") or hit.get("question")
        if isinstance(t, str) and t.strip():
            return t.strip()
    return None


def _mt(text: str, src: str, dst: str) -> str | None:
    if not text.strip():
        return ""
    if src == dst:
        return text
    pair = _LANGPAIR.get((src, dst))
    if not pair:
        return None
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                "https://api.mymemory.translated.net/get",
                params={"q": text[:450], "langpair": pair},
            )
            resp.raise_for_status()
            payload = resp.json()
        translated = (payload.get("responseData") or {}).get("translatedText") or ""
        translated = translated.strip()
        if not translated:
            return None
        if "INVALID" in translated.upper() and "LANGUAGE" in translated.upper():
            return None
        return translated
    except Exception as exc:  # noqa: BLE001
        log.warning("mt_failed src=%s dst=%s err=%s", src, dst, exc)
        return None


def view_text(db: Session, prompt: PromptItem, view: str) -> dict[str, Any]:
    """Return only the human utterance for a view locale (this prompt only)."""
    view = (view or prompt.source_locale or "en").lower()
    if view not in VIEW_LOCALES:
        view = prompt.source_locale if prompt.source_locale in VIEW_LOCALES else "en"

    src = (prompt.source_locale or "en").lower()
    if src not in VIEW_LOCALES:
        src = "en"

    text = (prompt.source_text or "").strip()

    if view == src:
        return {"locale": view, "text": text}

    cache = _load_cache(prompt)
    hit = _cached_text(cache.get(view))
    if hit:
        return {"locale": view, "text": hit}

    translated = _mt(text, src, view) or text
    cache[view] = {"text": translated}
    _save_cache(db, prompt, cache)
    return {"locale": view, "text": translated}
