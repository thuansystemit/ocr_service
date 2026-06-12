"""Webhook signing unit tests (T-055)."""

from __future__ import annotations

from app.domain.webhook import (
    SIGNATURE_HEADER,
    build_signed_request,
    serialize_payload,
    sign,
    verify,
)


def test_serialize_is_canonical() -> None:
    # Key order in the source dict must not change the signed bytes.
    a = serialize_payload({"b": 2, "a": 1})
    b = serialize_payload({"a": 1, "b": 2})
    assert a == b == b'{"a":1,"b":2}'


def test_sign_and_verify_round_trip() -> None:
    body = serialize_payload({"document_id": "abc", "status": "completed"})
    signature = sign(body, "secret-key")
    assert signature.startswith("sha256=")
    assert verify(body, "secret-key", signature) is True


def test_verify_rejects_tampered_body() -> None:
    body = serialize_payload({"amount": "100"})
    signature = sign(body, "secret-key")
    tampered = serialize_payload({"amount": "999"})
    assert verify(tampered, "secret-key", signature) is False


def test_verify_rejects_wrong_secret() -> None:
    body = serialize_payload({"x": 1})
    assert verify(body, "other-secret", sign(body, "secret-key")) is False


def test_build_signed_request_headers() -> None:
    body, headers = build_signed_request({"x": 1}, "secret-key")
    assert headers["Content-Type"] == "application/json"
    assert verify(body, "secret-key", headers[SIGNATURE_HEADER]) is True
