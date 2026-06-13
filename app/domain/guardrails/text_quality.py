"""Text-quality guardrail (T-047).

Flags parsed text that is too short or too garbled to extract from reliably. Empty
text is a hard BLOCK (nothing to extract); low word count or low printable-ratio
(a sign of a bad OCR/parse) is a WARN that downweights confidence so weak inputs
are less likely to straight-through-process.
"""

from __future__ import annotations

from app.domain.guardrails.base import GuardrailBase, GuardrailOutcome

_MIN_WORDS = 20
_MIN_PRINTABLE_RATIO = 0.80


class TextQualityGuardrail(GuardrailBase):
    name = "text_quality"

    def run(self, text: str) -> GuardrailOutcome:
        stripped = text.strip()
        if not stripped:
            return self._block("parsed text is empty")

        words = stripped.split()
        if len(words) < _MIN_WORDS:
            return self._warn(f"low word count: {len(words)} < {_MIN_WORDS}")

        printable = sum(1 for c in stripped if c.isprintable() or c.isspace())
        ratio = printable / len(stripped)
        if ratio < _MIN_PRINTABLE_RATIO:
            return self._warn(f"low printable ratio: {ratio:.2f}")

        return self._pass()
