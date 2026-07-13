"""FAQ chunking strategy (short, self-contained chunks preferred for FAQ)."""

from __future__ import annotations


def chunk_faq_text(text: str, *, chunk_size: int = 256, overlap: int = 32) -> list[str]:
    """Simple character-window chunker with overlap.

    FAQ items should ideally be one Q/A per chunk (see scripts/index_faq.py).
    This fallback splits long articles.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks
