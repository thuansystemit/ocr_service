"""DocumentParser interface and result type (C-11)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ParseResult:
    text: str
    method: str  # "local" | "llamaparse" | "ocr"
    page_count: int

    @property
    def is_empty(self) -> bool:
        """True when parsing yielded essentially no text (EC-006: empty/scanned
        PDF). The pipeline routes these to OCR / DLQ rather than the LLM."""
        return len(self.text.replace("\n", "").strip()) < 10


def clean_text(text: str) -> str:
    """Strip characters that downstream stores reject.

    PostgreSQL ``text``/``jsonb`` cannot represent the NUL byte (``\\u0000``), and
    some PDFs yield NUL bytes from pdfplumber. Since parsed text flows into the
    LangGraph state (checkpointed to Postgres JSONB) and the document record,
    every parser must scrub it here.
    """
    return text.replace("\x00", "")


class ParserError(RuntimeError):
    """Raised when a document cannot be parsed by any available method."""


class DocumentParser(Protocol):
    async def parse(self, content: bytes, *, mime_type: str | None = None) -> ParseResult:
        """Extract text from a document's raw bytes."""
        ...
