"""Document parsers (C-11): interface + backends + selector.

The ``DocumentParser`` interface abstracts the parse step so the deployment-time
choice between LlamaParse cloud, a self-hosted LlamaParse, and the local OCR
fallback (open decision I-003) is a config swap, not a code change. Sprint 3
ships the local backend; the LlamaParse cloud client is wired in Sprint 4
(T-038).
"""

from __future__ import annotations

from app.config import get_settings
from app.pipeline.parsers.base import DocumentParser, ParseResult
from app.pipeline.parsers.local import LocalParser

_parser: DocumentParser | None = None


def get_parser() -> DocumentParser:
    global _parser
    if _parser is None:
        backend = get_settings().parser_backend
        if backend == "local":
            _parser = LocalParser()
        elif backend == "llamaparse":
            from app.pipeline.parsers.llamaparse import LlamaParseClient

            _parser = LlamaParseClient()
        else:
            raise ValueError(f"unsupported parser backend: {backend}")
    return _parser


__all__ = ["DocumentParser", "LocalParser", "ParseResult", "get_parser"]
