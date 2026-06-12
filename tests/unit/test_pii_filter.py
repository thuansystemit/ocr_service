"""PII redaction processor unit tests."""

from __future__ import annotations

from app.observability.pii_filter import REDACTED, pii_redaction_processor


def _scrub(event: dict[str, object]) -> dict[str, object]:
    return pii_redaction_processor(None, "info", event)


def test_sensitive_keys_are_masked() -> None:
    out = _scrub({"event": "login", "api_key": "sk-123", "webhook_secret": "shh"})
    assert out["api_key"] == REDACTED
    assert out["webhook_secret"] == REDACTED
    assert out["event"] == "login"


def test_email_in_value_is_masked() -> None:
    out = _scrub({"event": "parsed", "text": "contact jane.doe@acme.com please"})
    assert "jane.doe@acme.com" not in out["text"]  # type: ignore[operator]
    assert REDACTED in out["text"]  # type: ignore[operator]


def test_nested_structures_are_scrubbed() -> None:
    out = _scrub({"meta": {"password": "p", "items": [{"token": "t"}]}})
    meta = out["meta"]
    assert meta["password"] == REDACTED  # type: ignore[index]
    assert meta["items"][0]["token"] == REDACTED  # type: ignore[index]


def test_non_sensitive_values_pass_through() -> None:
    out = _scrub({"event": "ok", "count": 3, "ratio": 0.85})
    assert out == {"event": "ok", "count": 3, "ratio": 0.85}
