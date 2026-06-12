"""PII field encryption unit tests (T-018)."""

from __future__ import annotations

import base64
import uuid

import pytest
from pydantic import SecretStr

from app.config import get_settings
from app.domain import encryption
from app.domain.encryption import (
    EncryptionError,
    decrypt_fields,
    decrypt_value,
    encrypt_fields,
    encrypt_value,
    is_encrypted,
)


@pytest.fixture
def pii_key() -> None:
    get_settings().pii_encryption_key = SecretStr(base64.b64encode(b"k" * 32).decode())
    encryption._tenant_key.cache_clear()
    yield
    encryption._tenant_key.cache_clear()


def test_round_trip(pii_key: None) -> None:
    tid = uuid.uuid4()
    env = encrypt_value("john.doe@acme.com", tid)
    assert is_encrypted(env)
    assert env != "john.doe@acme.com"
    assert decrypt_value(env, tid) == "john.doe@acme.com"


def test_encrypt_is_idempotent(pii_key: None) -> None:
    tid = uuid.uuid4()
    once = encrypt_value("secret", tid)
    twice = encrypt_value(once, tid)  # already encrypted -> unchanged
    assert once == twice


def test_wrong_tenant_cannot_decrypt(pii_key: None) -> None:
    env = encrypt_value("1234-5678", uuid.uuid4())
    with pytest.raises(EncryptionError):
        decrypt_value(env, uuid.uuid4())  # different tenant key + AAD


def test_encrypt_fields_only_touches_listed_paths(pii_key: None) -> None:
    tid = uuid.uuid4()
    data = {
        "vendor_name": "Acme",
        "buyer_tax_id": "TAX-9",
        "bank": {"iban": "DE89370400440532013000"},
    }
    out = encrypt_fields(data, ["buyer_tax_id", "bank.iban"], tid)

    assert out["vendor_name"] == "Acme"  # untouched
    assert is_encrypted(out["buyer_tax_id"])
    assert is_encrypted(out["bank"]["iban"])

    back = decrypt_fields(out, ["buyer_tax_id", "bank.iban"], tid)
    assert back["buyer_tax_id"] == "TAX-9"
    assert back["bank"]["iban"] == "DE89370400440532013000"


def test_decrypt_value_passthrough_for_plaintext(pii_key: None) -> None:
    assert decrypt_value("not-encrypted", uuid.uuid4()) == "not-encrypted"


def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings().pii_encryption_key = None
    encryption._tenant_key.cache_clear()
    with pytest.raises(EncryptionError):
        encrypt_value("x", uuid.uuid4())
