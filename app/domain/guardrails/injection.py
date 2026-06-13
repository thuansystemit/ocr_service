"""Prompt-injection detection guardrail (T-046, REQ-013).

Scans parsed document text for instructions aimed at the *LLM* rather than data to
extract ("ignore previous instructions", "system prompt:", role-play jailbreaks,
etc.). A hit BLOCKs: the text never reaches the model. This is heuristic and
deliberately conservative — false positives route to the DLQ for human review
rather than risking a hijacked extraction.
"""

from __future__ import annotations

import re

from app.domain.guardrails.base import GuardrailBase, GuardrailOutcome

_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?(system|previous)", re.IGNORECASE),
    re.compile(r"\b(system|developer)\s*prompt\s*[:=]", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|in)\b", re.IGNORECASE),
    re.compile(r"\bact\s+as\s+(a|an)\b.*\b(jailbreak|DAN|unrestricted)\b", re.IGNORECASE),
    re.compile(r"<\s*/?\s*(system|assistant|instructions?)\s*>", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+)?prompt", re.IGNORECASE),
]


class InjectionGuardrail(GuardrailBase):
    name = "injection"

    def run(self, text: str) -> GuardrailOutcome:
        for pattern in _PATTERNS:
            match = pattern.search(text)
            if match:
                return self._block(f"prompt-injection pattern matched: {match.group(0)[:60]!r}")
        return self._pass()
