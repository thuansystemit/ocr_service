"""Auth unit tests: API key hashing/cache (T-016) and JWT verification (T-015)."""

from __future__ import annotations

import datetime as dt
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services import auth
from app.services.auth import (
    AuthError,
    _TTLCache,
    generate_api_key,
    hash_api_key,
    verify_jwt,
)

# --------------------------------------------------------------------------- #
# API keys
# --------------------------------------------------------------------------- #


def test_hash_is_deterministic_sha256() -> None:
    assert hash_api_key("ocr_abc") == hash_api_key("ocr_abc")
    assert len(hash_api_key("ocr_abc")) == 64


def test_generate_api_key_shape() -> None:
    raw, prefix, key_hash = generate_api_key()
    assert raw.startswith("ocr_")
    assert len(prefix) == 8
    assert key_hash == hash_api_key(raw)


def test_ttl_cache_hit_and_expiry() -> None:
    cache = _TTLCache(ttl_s=1000)
    cache.set("k", None)
    hit, value = cache.get("k")
    assert hit is True
    assert value is None

    expired = _TTLCache(ttl_s=-1)  # already expired
    expired.set("k", None)
    hit, _ = expired.get("k")
    assert hit is False


# --------------------------------------------------------------------------- #
# JWT (RS256)
# --------------------------------------------------------------------------- #


@pytest.fixture
def rsa_keypair(monkeypatch: pytest.MonkeyPatch) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    monkeypatch.setattr(auth, "_load_public_key", lambda: public_pem)
    return private_pem


def _make_token(private_pem: str, **overrides: object) -> str:
    claims = {
        "sub": "user-1",
        "tenant_id": str(uuid.uuid4()),
        "iss": "ocr-platform",
        "aud": "ocr-api",
        "scopes": ["extract", "read"],
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
    }
    claims.update(overrides)
    return jwt.encode(claims, private_pem, algorithm="RS256")


def test_valid_jwt_resolves_tenant(rsa_keypair: str) -> None:
    tid = uuid.uuid4()
    token = _make_token(rsa_keypair, tenant_id=str(tid))
    ctx = verify_jwt(token)
    assert ctx.tenant_id == tid
    assert ctx.principal == "jwt:user-1"
    assert ctx.has_scope("extract")


def test_expired_jwt_rejected(rsa_keypair: str) -> None:
    token = _make_token(rsa_keypair, exp=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1))
    with pytest.raises(AuthError):
        verify_jwt(token)


def test_wrong_audience_rejected(rsa_keypair: str) -> None:
    token = _make_token(rsa_keypair, aud="someone-else")
    with pytest.raises(AuthError):
        verify_jwt(token)


def test_missing_tenant_claim_rejected(rsa_keypair: str) -> None:
    token = _make_token(rsa_keypair, tenant_id=None)
    with pytest.raises(AuthError):
        verify_jwt(token)
