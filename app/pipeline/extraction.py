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

from pydantic import BaseModel, Field, create_model

from app.observability.logging import get_logger
from app.pipeline.prompts import build_extraction_prompt, retrieve_examples

log = get_logger(__name__)


class LLMExtraction(BaseModel):
    """Normalised extraction result the rest of the pipeline consumes."""

    fields: dict[str, Any] = Field(default_factory=dict, description="Extracted field values")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="LLM self-reported confidence")
    low_confidence_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


def build_output_model(json_schema: dict[str, Any]) -> type[BaseModel]:
    """Build a per-schema structured-output model from a tenant's JSON Schema.

    The envelope's ``fields`` becomes a concrete nested model with one optional
    string per schema property, so constrained decoding actually forces the LLM to
    emit *those* fields (e.g. ``full_name``, ``email``) instead of accepting an
    empty free-form object — which is what weak local models do otherwise.
    """
    properties = json_schema.get("properties", {}) if isinstance(json_schema, dict) else {}
    field_defs: dict[str, Any] = {
        name: (str | None, Field(default=None, description=str(spec.get("description", name))))
        for name, spec in properties.items()
        if name.isidentifier()
    }
    fields_model: type[BaseModel] = create_model("ExtractedFields", **field_defs)
    return create_model(
        "DynamicExtraction",
        fields=(fields_model, ...),
        confidence=(float, Field(default=0.0, ge=0.0, le=1.0)),
        low_confidence_fields=(list[str], Field(default_factory=list)),
        missing_fields=(list[str], Field(default_factory=list)),
    )


def _coerce(raw: Any) -> LLMExtraction:
    """Normalise any structured-output result into an ``LLMExtraction``."""
    if isinstance(raw, LLMExtraction):
        return raw
    data = raw.model_dump() if isinstance(raw, BaseModel) else dict(raw)
    fields = data.get("fields") or {}
    if isinstance(fields, BaseModel):
        fields = fields.model_dump()
    # Drop nulls so empty values don't masquerade as extracted fields.
    fields = {k: v for k, v in fields.items() if v not in (None, "")}
    return LLMExtraction(
        fields=fields,
        confidence=float(data.get("confidence") or 0.0),
        low_confidence_fields=list(data.get("low_confidence_fields") or []),
        missing_fields=list(data.get("missing_fields") or []),
    )


class ExtractionChain:
    def __init__(self, model: Any | None = None) -> None:
        self._model = model

    async def _invoke(self, prompt: str, output_model: type[BaseModel]) -> Any:
        # Injected model (tests): use directly, no breaker/fallback.
        if self._model is not None:
            return await self._model.with_structured_output(output_model).ainvoke(prompt)

        # Production: primary (Claude) under a circuit breaker, GPT-4o fallback (T-062).
        from app.domain.llm import get_chat_model, get_fallback_chat_model, get_llm_breaker

        async def _primary() -> Any:
            return await get_chat_model().with_structured_output(output_model).ainvoke(prompt)

        try:
            return await get_llm_breaker().call(_primary)
        except Exception as exc:
            log.warning("extraction.fallback_to_secondary", error=str(exc))
            fallback = get_fallback_chat_model().with_structured_output(output_model)
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
        output_model = build_output_model(json_schema)
        result = _coerce(await self._invoke(prompt, output_model))
        log.info(
            "extraction.completed",
            field_count=len(result.fields),
            llm_confidence=result.confidence,
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
