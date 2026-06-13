"""Input guardrails (C-12): injection detection, text quality, and the runner.

Guardrails inspect the parsed text *before* it reaches the LLM. Each returns a
``GuardrailOutcome`` with a result of PASS / WARN / BLOCK:

* **BLOCK** halts the pipeline — the text never reaches the LLM, the document
  goes to the DLQ (EC-004).
* **WARN** proceeds but contributes a confidence multiplier (< 1.0); the product
  of all WARN multipliers downweights the final confidence (EC-004 / I-005).
* **PASS** is neutral (multiplier 1.0).
"""

from __future__ import annotations

from app.domain.guardrails.base import (
    GuardrailBase,
    GuardrailOutcome,
    GuardrailResult,
    aggregate_multiplier,
    has_block,
)
from app.domain.guardrails.injection import InjectionGuardrail
from app.domain.guardrails.text_quality import TextQualityGuardrail

DEFAULT_GUARDRAILS: list[GuardrailBase] = [InjectionGuardrail(), TextQualityGuardrail()]


def run_guardrails(text: str) -> list[GuardrailOutcome]:
    return [g.run(text) for g in DEFAULT_GUARDRAILS]


__all__ = [
    "DEFAULT_GUARDRAILS",
    "GuardrailBase",
    "GuardrailOutcome",
    "GuardrailResult",
    "InjectionGuardrail",
    "TextQualityGuardrail",
    "aggregate_multiplier",
    "has_block",
    "run_guardrails",
]
