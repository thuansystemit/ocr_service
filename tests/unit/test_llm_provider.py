"""LLM/embedding provider selection unit tests (Ollama support).

These only assert the factory builds the right class for each provider; they never
connect (constructing a ChatOllama / OllamaEmbeddings is offline). The anthropic
and openai branches are not constructed here because their clients validate an API
key at init.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.domain import embeddings, llm


@pytest.fixture
def _reset() -> None:
    settings = get_settings()
    saved = (
        settings.llm_provider,
        settings.llm_fallback_provider,
        settings.embedding_provider,
    )
    yield
    (
        settings.llm_provider,
        settings.llm_fallback_provider,
        settings.embedding_provider,
    ) = saved
    llm._model = None
    llm._fallback = None
    embeddings._embedder = None


def test_ollama_chat_model_selected(_reset: None) -> None:
    settings = get_settings()
    settings.llm_provider = "ollama"
    settings.ollama_base_url = "http://host.docker.internal:11434"
    settings.llm_primary_model = "llama3.1"
    llm._model = None

    model = llm.get_chat_model()
    assert model.__class__.__name__ == "ChatOllama"


def test_unknown_provider_raises(_reset: None) -> None:
    with pytest.raises(ValueError, match="unsupported LLM provider"):
        llm._build_model("not-a-provider", "x")


def test_ollama_embedder_selected(_reset: None) -> None:
    settings = get_settings()
    settings.embedding_provider = "ollama"
    embeddings._embedder = None

    embedder = embeddings.get_embedder()
    assert isinstance(embedder, embeddings.OllamaEmbedder)
