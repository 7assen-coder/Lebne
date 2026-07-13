"""Embedding provider — same model for FAQ index, query, and domain guardrail."""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from api.config import Settings, get_settings

_TOKEN = re.compile(r"\w+", re.UNICODE)


class EmbeddingProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._model = None

    def _hash_embed(self, text: str, dims: int = 384) -> list[float]:
        vec = [0.0] * dims
        for tok in _TOKEN.findall(text.lower()):
            h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
            vec[h % dims] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def _st_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.settings.embedding_model)
        return self._model

    def embed(self, text: str) -> list[float]:
        if self.settings.embedding_backend == "hash":
            return self._hash_embed(text)
        try:
            vec = self._st_model().encode(text, normalize_embeddings=True)
            return vec.tolist()
        except Exception:
            # Offline / missing weights — deterministic fallback
            return self._hash_embed(text)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if self.settings.embedding_backend == "hash":
            return [self._hash_embed(t) for t in texts]
        try:
            vecs = self._st_model().encode(texts, normalize_embeddings=True)
            return [v.tolist() for v in vecs]
        except Exception:
            return [self._hash_embed(t) for t in texts]

    @staticmethod
    def cosine(a: list[float], b: list[float]) -> float:
        return float(sum(x * y for x, y in zip(a, b, strict=False)))


@lru_cache
def get_embedder() -> EmbeddingProvider:
    return EmbeddingProvider()
