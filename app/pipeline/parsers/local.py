"""Local document parser (C-11 fallback path).

Extracts an embedded text layer with ``pdfplumber``; if a PDF has little/no
embedded text (scanned), falls back to OCR via ``pytesseract`` on rendered pages.
Needs no external service, so it is the default backend until the LlamaParse
hosting decision (I-003) is made. Blocking libraries run in a thread.
"""

from __future__ import annotations

import asyncio
import io

import pdfplumber

from app.observability.logging import get_logger
from app.pipeline.parsers.base import ParserError, ParseResult, clean_text

log = get_logger(__name__)


def _extract_pdf_text(content: bytes) -> tuple[str, int]:
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n\n".join(pages), len(pages)


def _ocr_pdf(content: bytes) -> tuple[str, int]:
    # Imported lazily: only scanned PDFs hit this path, and it pulls in Pillow.
    import pdfplumber as _pp
    import pytesseract

    pages: list[str] = []
    with _pp.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            image = page.to_image(resolution=200).original
            pages.append(pytesseract.image_to_string(image) or "")
    return "\n\n".join(pages), len(pages)


class LocalParser:
    async def parse(self, content: bytes, *, mime_type: str | None = None) -> ParseResult:
        if not content:
            raise ParserError("empty document content")
        try:
            text, page_count = await asyncio.to_thread(_extract_pdf_text, content)
        except Exception as exc:  # malformed PDF, unsupported, etc.
            raise ParserError(f"local parse failed: {exc}") from exc

        result = ParseResult(text=clean_text(text), method="local", page_count=page_count)
        if not result.is_empty:
            return result

        # No embedded text -> try OCR before giving up (EC-006).
        log.info("parser.local.ocr_fallback", page_count=page_count)
        try:
            ocr_text, ocr_pages = await asyncio.to_thread(_ocr_pdf, content)
        except Exception as exc:
            raise ParserError(f"OCR fallback failed: {exc}") from exc
        return ParseResult(text=clean_text(ocr_text), method="ocr", page_count=ocr_pages)
