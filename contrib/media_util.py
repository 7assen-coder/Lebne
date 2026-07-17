"""Safe media path helpers for crowd audio (disk + Neon blob)."""

from __future__ import annotations

import re
from pathlib import Path

MEDIA_DIR = Path("media/contrib_audio")
MAX_AUDIO_BYTES = 8_000_000

_AUDIO_MIME = {
    ".webm": "audio/webm",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
}

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")


def audio_basename(raw: str | None) -> str | None:
    """Return a safe basename only (no path traversal, no existence check)."""
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip().replace("\\", "/")
    if ".." in cleaned:
        return None
    name = Path(cleaned).name
    if not name or name in {".", ".."} or "/" in name:
        return None
    if not _SAFE_NAME.match(name):
        return None
    return name


def portable_audio_path(name: str) -> str:
    return f"media/contrib_audio/{name}"


def audio_media_type(name_or_path: str | Path) -> str:
    return _AUDIO_MIME.get(Path(name_or_path).suffix.lower(), "application/octet-stream")


def resolve_audio_file(raw: str | None) -> Path | None:
    """Return the on-disk audio file for a stored path, or None."""
    name = audio_basename(raw)
    if not name:
        return None
    root = MEDIA_DIR.resolve()
    candidate = (MEDIA_DIR / name).resolve()
    try:
        if not candidate.is_relative_to(root):
            return None
    except AttributeError:
        if root not in candidate.parents and candidate != root:
            return None
    if not candidate.is_file():
        return None
    return candidate


def safe_audio_path(raw: str | None) -> str | None:
    """Accept a basename that exists on disk under MEDIA_DIR (legacy helper)."""
    candidate = resolve_audio_file(raw)
    if not candidate:
        return None
    return portable_audio_path(candidate.name)
