"""LangChain LCEL extraction chain (C-13, T-041).

Wraps the chat model with structured output so the LLM returns a fixed envelope
(``LLMExtraction``) regardless of the per-tenant schema: the schema itself is
described in the prompt, and the model populates ``fields`` accordingly plus a
self-reported confidence used by the scorer.

The model is injectable (``ExtractionChain(model=...)``) so tests run without an
API key. ``model.with_structured_output`` is provider-agnostic across Claude and
GPT-4o.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.observability.logging import get_logger
from app.pipeline.prompts import build_extraction_prompt, retrieve_examples

log = get_logger(__name__)


class LLMExtraction(BaseModel):
    """Fixed envelope the model must return (via structured output)."""

    fields: dict[str, Any] = Field(default_factory=dict, description="Extracted field values")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="LLM self-reported confidence")
    low_confidence_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class ExtractionChain:
    def __init__(self, model: Any | None = None) -> None:
        self._model = model

    async def _invoke(self, prompt: str) -> Any:
        # Injected model (tests): use directly, no breaker/fallback.
        if self._model is not None:
            return await self._model.with_structured_output(LLMExtraction).ainvoke(prompt)

        # Production: primary (Claude) under a circuit breaker, GPT-4o fallback (T-062).
        from app.domain.llm import get_chat_model, get_fallback_chat_model, get_llm_breaker

        async def _primary() -> Any:
            return await get_chat_model().with_structured_output(LLMExtraction).ainvoke(prompt)

        try:
            return await get_llm_breaker().call(_primary)
        except Exception as exc:
            log.warning("extraction.fallback_to_secondary", error=str(exc))
            fallback = get_fallback_chat_model().with_structured_output(LLMExtraction)
            return await fallback.ainvoke(prompt)

    async def extract(
        self,
        *,
        tenant_id: str,
        schema_id: str,
        schema_name: str,
        json_schema: dict[str, Any],
        required_fields: list[str],
        text: str,
    ) -> LLMExtraction:
        examples = await retrieve_examples(tenant_id=tenant_id, schema_id=schema_id, text=text)
        prompt = build_extraction_prompt(
            text=text,
            schema_name=schema_name,
            json_schema=json_schema,
            required_fields=required_fields,
            examples=examples,
        )
        result = await self._invoke(prompt)
        if not isinstance(result, LLMExtraction):  # some providers return a dict
            result = LLMExtraction.model_validate(result)
        log.info(
            "extraction.completed", field_count=len(result.fields), llm_confidence=result.confidence
        )
        return result


_chain: ExtractionChain | None = None


def get_extraction_chain() -> ExtractionChain:
    global _chain
    if _chain is None:
        _chain = ExtractionChain()
    return _chain


def set_extraction_chain(chain: ExtractionChain | None) -> None:
    """Override the process extraction chain (tests; pass None to reset)."""
    global _chain
    _chain = chain
