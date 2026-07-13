"""Qdrant FAQ retriever — same embedding model for index and query."""

from __future__ import annotations

from typing import Any

from api.config import Settings
from rag.chunking import chunk_faq_text
from rag.embeddings import get_embedder


class FaqRetriever:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.embedder = get_embedder()
        self._fallback = [
            {
                "id": "faq-fees",
                "text": "Lebne transfer fees depend on corridor and amount. Check the in-app fee preview before confirming.",
            },
            {
                "id": "faq-languages",
                "text": "Lebne support agent understands Arabic, French, English, and Hassaniya.",
            },
        ]

    def _client(self):
        from qdrant_client import QdrantClient

        return QdrantClient(url=self.settings.qdrant_url)

    async def search(self, query: str, *, user_id: str) -> list[dict[str, Any]]:
        _ = user_id
        vector = self.embedder.embed(query)
        try:
            client = self._client()
            results = client.search(
                collection_name=self.settings.qdrant_collection,
                query_vector=vector,
                limit=self.settings.rag_top_k,
                score_threshold=self.settings.rag_score_threshold,
            )
            return [
                {
                    "id": str(hit.id),
                    "text": (hit.payload or {}).get("text", ""),
                    "score": float(hit.score),
                    "locale": (hit.payload or {}).get("locale"),
                }
                for hit in results
                if (hit.payload or {}).get("text")
            ]
        except Exception:
            return self._lexical_fallback(query)

    def _lexical_fallback(self, query: str) -> list[dict[str, Any]]:
        q = query.lower()
        hits = []
        for item in self._fallback:
            score = 0.9 if any(tok in item["text"].lower() for tok in q.split() if len(tok) > 3) else 0.4
            if score >= self.settings.rag_score_threshold:
                hits.append({**item, "score": score})
        return sorted(hits, key=lambda h: h["score"], reverse=True)[: self.settings.rag_top_k]

    def preview_chunks(self, text: str) -> list[str]:
        return chunk_faq_text(
            text,
            chunk_size=self.settings.chunk_size,
            overlap=self.settings.chunk_overlap,
        )
