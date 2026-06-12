"""PII masking for log output (D-010 / REQ: ``[REDACTED]`` in logs).

This is defense-in-depth: even if a caller accidentally logs a structured value
containing an email, national id, IBAN, or a field explicitly named like a
secret, the processor rewrites it before the log line is emitted. It is *not* a
substitute for not logging PII in the first place.
"""

from __future__ import annotations

import re
from typing import Any

from structlog.typing import EventDict, WrappedLogger

REDACTED = "[REDACTED]"

# Keys whose values are always masked regardless of content.
_SENSITIVE_KEY_RE = re.compile(
    r"(password|secret|token|api[_-]?key|authorization|webhook_secret"
    r"|key_hash|pii|ssn|tax_id|iban|card|cvv)",
    re.IGNORECASE,
)

# Value patterns masked wherever they appear in string values.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _mask_value(value: str) -> str:
    value = _EMAIL_RE.sub(REDACTED, value)
    value = _IBAN_RE.sub(REDACTED, value)
    value = _CARD_RE.sub(REDACTED, value)
    return value


def _scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: (REDACTED if _SENSITIVE_KEY_RE.search(str(k)) else _scrub(v)) for k, v in obj.items()
        }
    if isinstance(obj, list | tuple):
        return type(obj)(_scrub(v) for v in obj)
    if isinstance(obj, str):
        return _mask_value(obj)
    return obj


def pii_redaction_processor(
    _logger: WrappedLogger, _method: str, event_dict: EventDict
) -> EventDict:
    """structlog processor that masks PII in the event dict in place."""
    return _scrub(event_dict)
