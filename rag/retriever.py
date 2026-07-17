"""Qdrant FAQ retriever — same embedding model for index and query."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.config import Settings
from rag.chunking import chunk_faq_text
from rag.embeddings import get_embedder


class FaqRetriever:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.embedder = get_embedder()
        self._faq_path = Path("data/faq/faq.jsonl")

    def _client(self):
        from qdrant_client import QdrantClient

        return QdrantClient(url=self.settings.qdrant_url, check_compatibility=False)

    async def search(self, query: str, *, user_id: str) -> list[dict[str, Any]]:
        _ = user_id
        vector = self.embedder.embed(query)
        try:
            client = self._client()
            response = client.query_points(
                collection_name=self.settings.qdrant_collection,
                query=vector,
                limit=self.settings.rag_top_k,
                score_threshold=self.settings.rag_score_threshold,
                with_payload=True,
            )
            points = getattr(response, "points", None) or []
            return [
                {
                    "id": str(hit.id),
                    "text": (hit.payload or {}).get("text", ""),
                    "score": float(hit.score or 0.0),
                    "locale": (hit.payload or {}).get("locale"),
                }
                for hit in points
                if (hit.payload or {}).get("text")
            ]
        except Exception:
            return self._lexical_fallback(query)

    def _load_faq_rows(self) -> list[dict[str, Any]]:
        if not self._faq_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self._faq_path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    def _lexical_fallback(self, query: str) -> list[dict[str, Any]]:
        """Offline / Qdrant-down fallback over local FAQ JSONL."""
        q_tokens = [t for t in query.lower().split() if len(t) > 2]
        hits: list[dict[str, Any]] = []
        for row in self._load_faq_rows():
            blob = f"{row.get('question', '')} {row.get('answer', '')}".lower()
            overlap = sum(1 for t in q_tokens if t in blob)
            if overlap == 0:
                continue
            score = min(0.95, 0.35 + 0.15 * overlap)
            if score >= self.settings.rag_score_threshold:
                hits.append(
                    {
                        "id": row.get("id"),
                        "text": f"Q: {row.get('question', '')}\nA: {row.get('answer', '')}",
                        "score": score,
                        "locale": row.get("locale"),
                    }
                )
        return sorted(hits, key=lambda h: h["score"], reverse=True)[: self.settings.rag_top_k]

    def preview_chunks(self, text: str) -> list[str]:
        return chunk_faq_text(
            text,
            chunk_size=self.settings.chunk_size,
            overlap=self.settings.chunk_overlap,
        )
