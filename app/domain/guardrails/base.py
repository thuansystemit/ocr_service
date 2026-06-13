"""Guardrail interface, outcome type, and aggregation helpers (T-045)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

# WARN penalty applied to confidence (I-005: 0.8 default, needs eval validation).
WARN_MULTIPLIER = 0.8


class GuardrailResult(str, Enum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


@dataclass(frozen=True)
class GuardrailOutcome:
    name: str
    result: GuardrailResult
    detail: str | None = None
    confidence_multiplier: float = 1.0

    def as_state(self) -> dict[str, object]:
        return {
            "name": self.name,
            "result": self.result.value,
            "detail": self.detail,
            "confidence_multiplier": self.confidence_multiplier,
        }


class GuardrailBase(ABC):
    name: str = "guardrail"

    @abstractmethod
    def run(self, text: str) -> GuardrailOutcome: ...

    def _pass(self) -> GuardrailOutcome:
        return GuardrailOutcome(self.name, GuardrailResult.PASS)

    def _warn(self, detail: str, multiplier: float = WARN_MULTIPLIER) -> GuardrailOutcome:
        return GuardrailOutcome(self.name, GuardrailResult.WARN, detail, multiplier)

    def _block(self, detail: str) -> GuardrailOutcome:
        return GuardrailOutcome(self.name, GuardrailResult.BLOCK, detail, 1.0)


def has_block(outcomes: list[GuardrailOutcome]) -> bool:
    return any(o.result is GuardrailResult.BLOCK for o in outcomes)


def aggregate_multiplier(outcomes: list[GuardrailOutcome]) -> float:
    """Product of all WARN multipliers (PASS/BLOCK contribute 1.0)."""
    multiplier = 1.0
    for o in outcomes:
        if o.result is GuardrailResult.WARN:
            multiplier *= o.confidence_multiplier
    return round(multiplier, 4)
