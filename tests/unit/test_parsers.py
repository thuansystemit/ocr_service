"""LocalParser unit tests (T-022 / C-11)."""

from __future__ import annotations

import pytest

from app.pipeline.parsers.base import ParserError, ParseResult, clean_text
from app.pipeline.parsers.local import LocalParser
from tests.conftest import make_text_pdf


def test_clean_text_strips_nul_bytes() -> None:
    # PostgreSQL JSONB cannot store the NUL byte; parsed text must be scrubbed.
    assert clean_text("CI/CD work\x00 here\x00") == "CI/CD work here"
    assert "\x00" not in clean_text("a\x00b")


async def test_extracts_embedded_text() -> None:
    parser = LocalParser()
    result = await parser.parse(make_text_pdf("Invoice 7 Total 42.00"))
    assert result.method == "local"
    assert "Invoice 7" in result.text
    assert result.page_count == 1
    assert result.is_empty is False


async def test_empty_content_raises() -> None:
    with pytest.raises(ParserError):
        await LocalParser().parse(b"")


async def test_garbage_raises_parser_error() -> None:
    with pytest.raises(ParserError):
        await LocalParser().parse(b"this is not a pdf at all")


def test_parse_result_is_empty_threshold() -> None:
    assert ParseResult(text="   \n ", method="local", page_count=1).is_empty is True
    assert ParseResult(text="enough text here", method="local", page_count=1).is_empty is False
