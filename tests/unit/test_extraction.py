"""Extraction chain + prompt builder unit tests (T-040/041)."""

from __future__ import annotations

from typing import Any

from app.pipeline.extraction import ExtractionChain, LLMExtraction
from app.pipeline.prompts import build_extraction_prompt


class _FakeStructured:
    def __init__(self, result: LLMExtraction) -> None:
        self._result = result

    async def ainvoke(self, _: Any) -> LLMExtraction:
        return self._result


class _FakeModel:
    """Mimics a LangChain chat model's structured-output runnable."""

    def __init__(self, result: LLMExtraction) -> None:
        self._result = result
        self.seen_schema: Any = None

    def with_structured_output(self, schema: Any) -> _FakeStructured:
        self.seen_schema = schema
        return _FakeStructured(self._result)


def test_prompt_includes_schema_required_and_examples() -> None:
    prompt = build_extraction_prompt(
        text="DOC BODY",
        schema_name="invoice",
        json_schema={"type": "object", "properties": {"total": {"type": "string"}}},
        required_fields=["total"],
        examples=[{"input_text": "EX IN", "expected_json": {"total": "5"}}],
    )
    assert "invoice" in prompt
    assert "Required fields: total" in prompt
    assert "EX IN" in prompt  # few-shot example injected
    assert "DOC BODY" in prompt


async def test_chain_returns_structured_extraction() -> None:
    expected = LLMExtraction(fields={"total": "42.00"}, confidence=0.9)
    model = _FakeModel(expected)
    chain = ExtractionChain(model=model)

    result = await chain.extract(
        tenant_id="t",
        schema_id="s",
        schema_name="invoice",
        json_schema={},
        required_fields=[],
        text="some invoice text",
    )
    assert result.fields == {"total": "42.00"}
    assert result.confidence == 0.9
    assert model.seen_schema is LLMExtraction


async def test_chain_coerces_dict_result() -> None:
    # Some providers return a dict rather than the model instance.
    model = _FakeModel(LLMExtraction(fields={"a": "1"}, confidence=0.5))
    # Force the dict branch by handing back a plain dict.
    model.with_structured_output = lambda schema: _FakeStructured(  # type: ignore[assignment, return-value]
        {"fields": {"a": "1"}, "confidence": 0.5}
    )
    chain = ExtractionChain(model=model)
    result = await chain.extract(
        tenant_id="t", schema_id="s", schema_name="x", json_schema={}, required_fields=[], text="t"
    )
    assert isinstance(result, LLMExtraction)
    assert result.fields == {"a": "1"}
