"""LLM factory (C-13).

Returns a LangChain ``BaseChatModel`` so the extraction chain is provider-agnostic
(D-007). Primary is Anthropic Claude; the GPT-4o fallback + circuit breaker are
wired in Sprint 5 (T-062). Models are built lazily so importing this never
requires an API key, and the active model is overridable for tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

_model: BaseChatModel | None = None


def get_chat_model() -> BaseChatModel:
    global _model
    if _model is None:
        from langchain_anthropic import ChatAnthropic

        settings = get_settings()
        _model = ChatAnthropic(model=settings.llm_primary_model, temperature=0)
    return _model


def set_chat_model(model: BaseChatModel | None) -> None:
    """Override the process chat model (tests; pass None to reset)."""
    global _model
    _model = model
