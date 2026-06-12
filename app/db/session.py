"""Async SQLAlchemy engine + session factory with tenant-scoped RLS (D-003).

Every unit of work that touches tenant data must run inside
:func:`tenant_session`, which issues ``SET LOCAL app.current_tenant_id = '<uuid>'``
on the connection. PostgreSQL RLS policies (migration 002) read that session
variable; without it, tenant-scoped tables return zero rows under the
non-superuser ``ocr_app`` role. ``SET LOCAL`` is transaction-scoped, so the
value never leaks to the next checkout of a pooled connection.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def dispose_engine() -> None:
    """Dispose the engine on shutdown (call from app lifespan)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


def _validate_tenant_id(tenant_id: UUID | str) -> str:
    """Coerce to a canonical UUID string (defense-in-depth on the tenant context
    value, on top of the bind parameter used by ``set_config``)."""
    return str(UUID(str(tenant_id)))


@contextlib.asynccontextmanager
async def tenant_session(tenant_id: UUID | str) -> AsyncIterator[AsyncSession]:
    """Yield a session bound to ``tenant_id`` for RLS enforcement.

    Commits on success, rolls back on exception. ``set_config(..., is_local =>
    true)`` is the transaction-scoped equivalent of ``SET LOCAL`` but, unlike the
    ``SET`` statement, it accepts a bind parameter -- so RLS sees the tenant
    context and the value is never string-interpolated into SQL.
    """
    safe_tenant = _validate_tenant_id(tenant_id)
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true)"),
            {"tid": safe_tenant},
        )
        yield session


@contextlib.asynccontextmanager
async def admin_session() -> AsyncIterator[AsyncSession]:
    """Yield a session WITHOUT tenant scoping.

    Only for cross-tenant operations executed by privileged code paths (GDPR
    erasure, retention purge, auth-time tenant lookup). RLS still applies unless
    the connection uses a BYPASSRLS role; callers must not use this to sidestep
    isolation for ordinary request handling.
    """
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        yield session
