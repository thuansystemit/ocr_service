"""Tenant request context (C-06).

A ``ContextVar`` carries the authenticated tenant id through the async call stack
so that code far from the request handler (logging, the DB session factory) can
read it without it being threaded through every call. The DB session factory
binds the same value into the PostgreSQL session variable that RLS reads.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from uuid import UUID

_current_tenant_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_tenant_id", default=None
)


@dataclass(frozen=True)
class AuthContext:
    """The result of authenticating a request."""

    tenant_id: UUID
    principal: str  # "apikey:<prefix>" or "jwt:<sub>"
    scopes: tuple[str, ...] = field(default_factory=tuple)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def set_current_tenant(tenant_id: UUID | str) -> contextvars.Token[str | None]:
    return _current_tenant_id.set(str(tenant_id))


def get_current_tenant() -> str | None:
    return _current_tenant_id.get()


def reset_current_tenant(token: contextvars.Token[str | None]) -> None:
    _current_tenant_id.reset(token)
