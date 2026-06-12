"""Confidence scoring (C-09, T-051).

Overall confidence is the **minimum** of three independent signals, multiplied by
the guardrail penalty:

    confidence = min(llm_self, completeness, semantic) x guardrail_multiplier

Taking the min (not the average) means any one weak signal drags the score down —
the conservative choice for an extraction platform where a single wrong field can
invalidate a document. Thresholds (HIGH ≥ 0.85, MEDIUM ≥ 0.60) are inclusive on
the upper tier (EC-003) and configurable per schema.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfidenceBreakdown:
    llm: float
    completeness: float
    semantic: float
    guardrail_adjusted: float

    def as_dict(self) -> dict[str, float]:
        return {
            "llm": self.llm,
            "completeness": self.completeness,
            "semantic": self.semantic,
            "guardrail_adjusted": self.guardrail_adjusted,
        }


def completeness_score(extracted: dict[str, object], required_fields: list[str]) -> float:
    """Fraction of required fields present and non-empty (1.0 if none required)."""
    if not required_fields:
        return 1.0
    present = sum(1 for f in required_fields if _is_present(extracted.get(f)))
    return present / len(required_fields)


def _is_present(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def missing_required(extracted: dict[str, object], required_fields: list[str]) -> list[str]:
    return [f for f in required_fields if not _is_present(extracted.get(f))]


def score(
    *,
    llm_self: float,
    completeness: float,
    semantic: float,
    guardrail_multiplier: float = 1.0,
) -> ConfidenceBreakdown:
    base = min(llm_self, completeness, semantic)
    adjusted = round(base * guardrail_multiplier, 4)
    return ConfidenceBreakdown(
        llm=round(llm_self, 4),
        completeness=round(completeness, 4),
        semantic=round(semantic, 4),
        guardrail_adjusted=adjusted,
    )


def route(confidence: float, *, high: float = 0.85, medium: float = 0.60) -> str:
    """Map a confidence to HIGH/MEDIUM/LOW (upper-tier inclusive, EC-003)."""
    if confidence >= high:
        return "HIGH"
    if confidence >= medium:
        return "MEDIUM"
    return "LOW"
