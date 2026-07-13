#!/usr/bin/env python3
"""Index FAQ sources into Qdrant. Re-run after FAQ updates."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from api.config import get_settings
from rag.chunking import chunk_faq_text
from rag.embeddings import EmbeddingProvider


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("data/faq/faq.jsonl"))
    parser.add_argument("--collection", default=None)
    parser.add_argument("--recreate", action="store_true")
    args = parser.parse_args()

    if not args.source.exists():
        raise SystemExit(f"Missing FAQ source: {args.source}")

    settings = get_settings()
    collection = args.collection or settings.qdrant_collection
    embedder = EmbeddingProvider(settings)

    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qm

    client = QdrantClient(url=settings.qdrant_url)
    sample_dim = len(embedder.embed("dimension probe"))

    if args.recreate and client.collection_exists(collection):
        client.delete_collection(collection)

    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config=qm.VectorParams(size=sample_dim, distance=qm.Distance.COSINE),
        )

    points = []
    texts: list[str] = []
    payloads: list[dict] = []
    with args.source.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            body = f"Q: {row.get('question', '')}\nA: {row.get('answer', '')}".strip()
            for i, chunk in enumerate(
                chunk_faq_text(body, chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)
            ):
                texts.append(chunk)
                payloads.append(
                    {
                        "text": chunk,
                        "faq_id": row.get("id"),
                        "locale": row.get("locale"),
                        "version": row.get("version", 1),
                        "chunk": i,
                    }
                )

    vectors = embedder.embed_many(texts)
    for text, payload, vector in zip(texts, payloads, vectors, strict=True):
        points.append(
            qm.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{payload['faq_id']}:{payload['chunk']}:{text[:32]}")),
                vector=vector,
                payload=payload,
            )
        )

    if points:
        client.upsert(collection_name=collection, points=points)

    print(f"Indexed {len(points)} chunks into `{collection}` (dim={sample_dim}).")
    print("Re-run this script after FAQ updates; bump version in faq.jsonl.")


if __name__ == "__main__":
    main()
