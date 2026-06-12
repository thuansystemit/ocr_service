"""Field-level PII encryption (C-08, D-010, REQ-031).

AES-256-GCM with a **per-tenant** key derived from a single master key via HKDF.
The tenant id is also bound in as GCM associated data, so a ciphertext produced
for tenant A cannot be decrypted under tenant B's context even if the rows were
somehow swapped -- a defense-in-depth complement to RLS.

Envelope format (stored in place of the plaintext field value):

    ocrenc:v1:<base64(nonce(12) || ciphertext+tag)>

``encrypt_fields`` / ``decrypt_fields`` walk a dict and transform only the listed
``pii_fields`` (dotted paths supported for nested objects), leaving everything
else untouched. Encryption is idempotent-safe: an already-encrypted value is not
re-encrypted, and decrypting a non-envelope value returns it unchanged.
"""

from __future__ import annotations

import base64
import os
from copy import deepcopy
from functools import lru_cache
from typing import Any
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings

_PREFIX = "ocrenc:v1:"
_NONCE_BYTES = 12
_KEY_BYTES = 32


class EncryptionError(RuntimeError):
    """Raised when encryption/decryption cannot proceed."""


def _master_key() -> bytes:
    settings = get_settings()
    if settings.pii_encryption_key is None:
        raise EncryptionError("OCR_PII_ENCRYPTION_KEY is not set; refusing to handle PII fields.")
    raw = base64.b64decode(settings.pii_encryption_key.get_secret_value())
    if len(raw) != _KEY_BYTES:
        raise EncryptionError(
            f"OCR_PII_ENCRYPTION_KEY must decode to {_KEY_BYTES} bytes, got {len(raw)}."
        )
    return raw


@lru_cache(maxsize=512)
def _tenant_key(tenant_id: str) -> bytes:
    """Derive a stable per-tenant 256-bit key from the master key (HKDF-SHA256)."""
    canonical = str(UUID(tenant_id)).encode()
    hkdf = HKDF(algorithm=SHA256(), length=_KEY_BYTES, salt=canonical, info=b"ocr-pii-field")
    return hkdf.derive(_master_key())


def is_encrypted(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_value(plaintext: str, tenant_id: str | UUID) -> str:
    if is_encrypted(plaintext):
        return plaintext
    tid = str(tenant_id)
    aes = AESGCM(_tenant_key(tid))
    nonce = os.urandom(_NONCE_BYTES)
    ct = aes.encrypt(nonce, plaintext.encode(), str(UUID(tid)).encode())
    return _PREFIX + base64.b64encode(nonce + ct).decode()


def decrypt_value(envelope: str, tenant_id: str | UUID) -> str:
    if not is_encrypted(envelope):
        return envelope
    tid = str(tenant_id)
    blob = base64.b64decode(envelope[len(_PREFIX) :])
    nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    try:
        aes = AESGCM(_tenant_key(tid))
        return aes.decrypt(nonce, ct, str(UUID(tid)).encode()).decode()
    except Exception as exc:  # InvalidTag etc.
        raise EncryptionError("PII decryption failed (wrong tenant key or tampered data)") from exc


def _walk(data: dict[str, Any], path: str, transform: Any) -> None:
    """Apply ``transform`` to the leaf at dotted ``path`` within ``data`` in place."""
    head, _, rest = path.partition(".")
    if head not in data:
        return
    if rest:
        child = data[head]
        if isinstance(child, dict):
            _walk(child, rest, transform)
        return
    value = data[head]
    if isinstance(value, str):
        data[head] = transform(value)


def encrypt_fields(
    data: dict[str, Any], pii_fields: list[str], tenant_id: str | UUID
) -> dict[str, Any]:
    """Return a copy of ``data`` with each ``pii_fields`` leaf encrypted."""
    out = deepcopy(data)
    for field in pii_fields:
        _walk(out, field, lambda v: encrypt_value(v, tenant_id))
    return out


def decrypt_fields(
    data: dict[str, Any], pii_fields: list[str], tenant_id: str | UUID
) -> dict[str, Any]:
    """Return a copy of ``data`` with each ``pii_fields`` leaf decrypted."""
    out = deepcopy(data)
    for field in pii_fields:
        _walk(out, field, lambda v: decrypt_value(v, tenant_id))
    return out
