"""Webhook payload signing (T-055, REQ-011).

The result payload is signed with HMAC-SHA256 using the tenant's
``webhook_secret`` and the signature is sent in ``X-OCR-Signature`` so receivers
can verify authenticity. Signing is over the exact serialized bytes that go on
the wire (canonical JSON, sorted keys) so the receiver can recompute it
deterministically. Async delivery + retry [1,5,30,120,600]s is the Sprint 5
delivery node (T-056); this module is the pure, testable signing core.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

SIGNATURE_HEADER = "X-OCR-Signature"


def serialize_payload(payload: dict[str, Any]) -> bytes:
    """Canonical JSON bytes (sorted keys, compact) — the signed representation."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify(body: bytes, secret: str, signature: str) -> bool:
    return hmac.compare_digest(sign(body, secret), signature)


def build_signed_request(payload: dict[str, Any], secret: str) -> tuple[bytes, dict[str, str]]:
    """Return ``(body_bytes, headers)`` ready to POST to the tenant webhook."""
    body = serialize_payload(payload)
    return body, {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: sign(body, secret),
    }
