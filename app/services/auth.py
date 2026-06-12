"""Authentication: API keys (T-016) and JWT RS256 (T-015).

Two credential types resolve to the same :class:`AuthContext`:

* **API key** -- ``Authorization: Bearer ocr_<...>``. The key is SHA-256 hashed
  and resolved to a tenant via the ``auth_resolve_api_key`` SECURITY DEFINER
  function (migration 004). Hot keys are cached in-process for 60s to keep the
  p95 lookup well under 100ms (REQ-032).
* **JWT** -- ``Authorization: Bearer <jwt>``, verified with an RS256 public key;
  ``tenant_id`` is read from the signed claim, so no DB lookup is needed.

Resolution never trusts unsigned input: a revoked or expired key is rejected, and
a JWT failing signature/issuer/audience/expiry checks is rejected.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import time
from pathlib import Path
from uuid import UUID

import jwt
from sqlalchemy import text

from app.api.context import AuthContext
from app.config import get_settings
from app.db.session import get_sessionmaker
from app.observability.logging import get_logger

log = get_logger(__name__)

_API_KEY_PREFIX = "ocr_"
_CACHE_TTL_S = 60.0


class AuthError(Exception):
    """Raised when a credential is missing, malformed, or invalid."""


# --------------------------------------------------------------------------- #
# API keys
# --------------------------------------------------------------------------- #
def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Mint a new key. Returns ``(raw_key, key_prefix, key_hash)``.

    Only ``key_prefix`` and ``key_hash`` are stored; ``raw_key`` is shown to the
    caller once and never persisted.
    """
    token = secrets.token_urlsafe(32)
    raw_key = f"{_API_KEY_PREFIX}{token}"
    return raw_key, token[:8], hash_api_key(raw_key)


class _TTLCache:
    """Minimal in-process TTL cache for resolved API keys."""

    def __init__(self, ttl_s: float, maxsize: int = 1024) -> None:
        self._ttl = ttl_s
        self._maxsize = maxsize
        self._data: dict[str, tuple[float, AuthContext | None]] = {}

    def get(self, key: str) -> tuple[bool, AuthContext | None]:
        item = self._data.get(key)
        if item is None:
            return False, None
        expires, value = item
        if time.monotonic() > expires:
            self._data.pop(key, None)
            return False, None
        return True, value

    def set(self, key: str, value: AuthContext | None) -> None:
        if len(self._data) >= self._maxsize:
            self._data.clear()  # simple eviction; fine at this scale
        self._data[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        self._data.clear()


_key_cache = _TTLCache(_CACHE_TTL_S)


async def resolve_api_key(raw_key: str) -> AuthContext:
    key_hash = hash_api_key(raw_key)
    cached, value = _key_cache.get(key_hash)
    if cached:
        if value is None:
            raise AuthError("invalid API key")
        return value

    prefix = raw_key[len(_API_KEY_PREFIX) : len(_API_KEY_PREFIX) + 8]
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        row = (
            await session.execute(
                text(
                    "SELECT tenant_id, scopes, expires_at, revoked_at "
                    "FROM auth_resolve_api_key(:h)"
                ),
                {"h": key_hash},
            )
        ).first()

    if row is None or row.revoked_at is not None or _expired(row.expires_at):
        _key_cache.set(key_hash, None)
        raise AuthError("invalid API key")

    ctx = AuthContext(
        tenant_id=row.tenant_id,
        principal=f"apikey:{prefix}",
        scopes=tuple(row.scopes or ()),
    )
    _key_cache.set(key_hash, ctx)
    return ctx


def _expired(expires_at: dt.datetime | None) -> bool:
    return expires_at is not None and expires_at <= dt.datetime.now(dt.UTC)


# --------------------------------------------------------------------------- #
# JWT (RS256)
# --------------------------------------------------------------------------- #
_public_key_cache: str | None = None


def _load_public_key() -> str | None:
    global _public_key_cache
    if _public_key_cache is not None:
        return _public_key_cache
    path = Path(get_settings().jwt_public_key_path)
    if not path.exists():
        return None
    _public_key_cache = path.read_text()
    return _public_key_cache


def verify_jwt(token: str) -> AuthContext:
    public_key = _load_public_key()
    if public_key is None:
        raise AuthError("JWT auth is not configured")
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid JWT: {exc}") from exc

    tenant_raw = claims.get("tenant_id")
    if not tenant_raw:
        raise AuthError("JWT missing tenant_id claim")
    try:
        tenant_id = UUID(str(tenant_raw))
    except ValueError as exc:
        raise AuthError("JWT tenant_id is not a valid UUID") from exc

    scopes = claims.get("scopes") or []
    sub = claims.get("sub", "unknown")
    return AuthContext(tenant_id=tenant_id, principal=f"jwt:{sub}", scopes=tuple(scopes))


# --------------------------------------------------------------------------- #
# Unified entry point
# --------------------------------------------------------------------------- #
async def authenticate(authorization: str | None) -> AuthContext:
    """Resolve an ``Authorization`` header value to an AuthContext or raise."""
    if not authorization:
        raise AuthError("missing Authorization header")
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credential:
        raise AuthError("expected 'Bearer <token>' authorization")

    if credential.startswith(_API_KEY_PREFIX):
        return await resolve_api_key(credential)
    return verify_jwt(credential)
