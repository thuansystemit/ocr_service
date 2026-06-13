"""Audit service (C-07, T-071, REQ-036/037).

``append_event`` writes one immutable row to ``audit_log`` for every
state-changing operation. The payload is hashed (SHA-256 of canonical JSON) and
only the hash is stored — the audit trail proves *what* happened and that the
payload wasn't altered, without itself becoming a second copy of PII. The table's
PG triggers (migration 003) make these rows append-only.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


def payload_hash(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def append_event(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    event_type: str,
    actor: str,
    document_id: UUID | None = None,
    status: str | None = None,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append one audit event within the caller's transaction.

    Runs in the same session/transaction as the operation it records, so the
    event and the change commit (or roll back) atomically.
    """
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            document_id=document_id,
            event_type=event_type,
            actor=actor,
            status=status,
            payload_hash=payload_hash(payload),
            audit_metadata=metadata,
        )
    )
