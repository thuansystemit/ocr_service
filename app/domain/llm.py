"""LLM factory (C-13).

Returns a LangChain ``BaseChatModel`` so the extraction chain is provider-agnostic
(D-007). Three providers are selectable via ``OCR_LLM_PROVIDER`` /
``OCR_LLM_FALLBACK_PROVIDER``: ``anthropic`` (Claude), ``openai`` (GPT-4o), and
``ollama`` (local/self-hosted, ``OCR_OLLAMA_BASE_URL``). The fallback model is
used when the primary trips the circuit breaker (T-062). Models are built lazily
so importing this never requires an API key, and the active model is overridable
for tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import get_settings
from app.domain.circuit_breaker import CircuitBreaker

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

_model: BaseChatModel | None = None
_fallback: BaseChatModel | None = None
_breaker = CircuitBreaker(name="llm-primary")


def _build_model(provider: str, model: str) -> BaseChatModel:
    settings = get_settings()
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, temperature=0)
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, temperature=0)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, base_url=settings.ollama_base_url, temperature=0)
    raise ValueError(f"unsupported LLM provider: {provider!r} (use anthropic|openai|ollama)")


def get_chat_model() -> BaseChatModel:
    global _model
    if _model is None:
        settings = get_settings()
        _model = _build_model(settings.llm_provider, settings.llm_primary_model)
    return _model


def get_fallback_chat_model() -> BaseChatModel:
    global _fallback
    if _fallback is None:
        settings = get_settings()
        _fallback = _build_model(settings.llm_fallback_provider, settings.llm_fallback_model)
    return _fallback


def get_llm_breaker() -> CircuitBreaker:
    return _breaker


def set_chat_model(model: BaseChatModel | None) -> None:
    """Override the process chat model (tests; pass None to reset)."""
    global _model
    _model = model
