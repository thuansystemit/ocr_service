"""Shared test doubles for the external RAG dependencies (embeddings + Qdrant)."""

from __future__ import annotations

from typing import Any


class FakeEmbedder:
    async def embed(self, text: str) -> list[float]:
        return [0.0] * 8


class FakeQdrant:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []
        self.deletes: list[dict[str, Any]] = []

    async def upsert_example(self, **kwargs: Any) -> None:
        self.upserts.append(kwargs)

    async def search(self, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    async def delete_by_document(self, **kwargs: Any) -> None:
        self.deletes.append(kwargs)
