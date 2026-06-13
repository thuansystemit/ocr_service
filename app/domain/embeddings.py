"""Text embeddings abstraction (used by RAG retrieval + semantic scoring).

A thin ``Embedder`` protocol so the rest of the code never imports a provider
directly. Production uses OpenAI ``text-embedding-3-small`` (1536-dim, matches the
Qdrant collection); tests inject a deterministic fake. The provider is created
lazily so importing this module never requires an API key.
"""

from __future__ import annotations

from typing import Protocol

from app.config import get_settings


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class OpenAIEmbedder:
    def __init__(self, model: str = "text-embedding-3-small") -> None:
        self._model = model
        self._client: object | None = None

    def _ensure_client(self) -> object:
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI()
        return self._client

    async def embed(self, text: str) -> list[float]:
        client = self._ensure_client()
        resp = await client.embeddings.create(model=self._model, input=text)  # type: ignore[attr-defined]
        return list(resp.data[0].embedding)


class OllamaEmbedder:
    """Embeddings from a local/self-hosted Ollama instance (``OCR_OLLAMA_BASE_URL``)."""

    def __init__(self, model: str, base_url: str) -> None:
        self._model = model
        self._base_url = base_url
        self._client: object | None = None

    def _ensure_client(self) -> object:
        if self._client is None:
            from langchain_ollama import OllamaEmbeddings

            self._client = OllamaEmbeddings(model=self._model, base_url=self._base_url)
        return self._client

    async def embed(self, text: str) -> list[float]:
        client = self._ensure_client()
        return await client.aembed_query(text)  # type: ignore[attr-defined]


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        settings = get_settings()
        if settings.embedding_provider == "ollama":
            _embedder = OllamaEmbedder(settings.ollama_embedding_model, settings.ollama_base_url)
        else:
            _embedder = OpenAIEmbedder()
    return _embedder


def set_embedder(embedder: Embedder | None) -> None:
    """Override the process embedder (used by tests; pass None to reset)."""
    global _embedder
    _embedder = embedder


def expected_dim() -> int:
    return get_settings().embedding_dim
