"""FastAPI dependencies for auth and tenant-scoped DB access (C-06, T-017).

``require_auth`` authenticates the request and binds the tenant into the logging
context. ``get_session`` builds on it to yield a DB session already scoped to the
caller's tenant (RLS enforced), and also publishes the tenant id into the
``ContextVar`` so non-request code can read it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.context import AuthContext, reset_current_tenant, set_current_tenant
from app.db.session import tenant_session
from app.observability.logging import bind_context
from app.services.auth import AuthError, authenticate


async def require_auth(authorization: str | None = Header(default=None)) -> AuthContext:
    try:
        ctx = await authenticate(authorization)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    bind_context(tenant_id=str(ctx.tenant_id), principal=ctx.principal)
    return ctx


def require_scope(scope: str) -> Callable[..., Awaitable[AuthContext]]:
    """Build a dependency that enforces the given scope on the authenticated key."""

    async def _checker(auth: AuthContext = Depends(require_auth)) -> AuthContext:
        if not auth.has_scope(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing required scope: {scope}",
            )
        return auth

    return _checker


async def get_session(
    auth: AuthContext = Depends(require_auth),
) -> AsyncIterator[AsyncSession]:
    token = set_current_tenant(auth.tenant_id)
    try:
        async with tenant_session(auth.tenant_id) as session:
            yield session
    finally:
        reset_current_tenant(token)
