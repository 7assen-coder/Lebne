"""Safe media path helpers for crowd audio."""

from __future__ import annotations

from pathlib import Path

MEDIA_DIR = Path("media/contrib_audio")
MAX_AUDIO_BYTES = 8_000_000


def safe_audio_path(raw: str | None) -> str | None:
    """Accept only a basename that already exists under MEDIA_DIR (no traversal)."""
    if not raw or not isinstance(raw, str):
        return None
    name = Path(raw).name
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
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
    # Store portable relative path
    return f"media/contrib_audio/{name}"
