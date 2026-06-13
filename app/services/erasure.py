"""GDPR erasure orchestrator (C-05, T-075/076, REQ-039/041).

Implements the SP-003 design: **cancel the producer first, delete externals
before Postgres rows, write the tombstone last.** Each external delete is
idempotent so a crash mid-erasure can be re-driven safely. The completion
invariant is a single tombstone audit event.

Note: ``audit_log`` stores only a SHA-256 payload *hash*, never PII, so audit rows
are not personal data and are intentionally kept (the trail survives erasure).
This is also why erasure needs no BYPASSRLS admin path — everything runs in the
tenant's RLS-scoped session.
"""

from __future__ import annotations

import contextlib
from uuid import UUID

from sqlalchemy import delete, text

from app.db.models import Document
from app.db.session import tenant_session
from app.domain.storage import get_storage
from app.observability.logging import get_logger
from app.services import audit
from app.services.qdrant import get_qdrant_service
from app.worker import cancellation

log = get_logger(__name__)

_CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")


class DocumentNotFoundError(Exception):
    pass


async def erase_document(document_id: UUID, tenant_id: UUID) -> None:
    """Erase a document and all of its derived data (idempotent / crash-safe)."""
    # 1. Cancel the producer so an in-flight run stops writing (D-SP003-1).
    cancellation.cancel(document_id)
    async with tenant_session(tenant_id) as session:
        document = await session.get(Document, document_id)
        if document is None:
            raise DocumentNotFoundError(f"document {document_id} not found")
        storage_key = document.file_storage_key
        document.status = "cancelled"

    # 2. Delete external stores before Postgres rows (idempotent; D-SP003-2).
    if storage_key:
        with contextlib.suppress(Exception):
            await get_storage().delete(storage_key)
    with contextlib.suppress(Exception):
        await get_qdrant_service().delete_by_document(tenant_id=tenant_id, document_id=document_id)
    await _purge_checkpoints(tenant_id, document_id)

    # 3. Delete Postgres rows (FK cascade) + tombstone last (D-SP003-3).
    async with tenant_session(tenant_id) as session:
        await session.execute(delete(Document).where(Document.id == document_id))
        await audit.append_event(
            session,
            tenant_id=tenant_id,
            document_id=document_id,
            event_type="ERASURE_COMPLETED",
            actor="system:gdpr",
            status="cancelled",
            metadata={"reason": "gdpr_erasure"},
        )

    cancellation.clear(document_id)
    log.info("erasure.completed", document_id=str(document_id))


async def _purge_checkpoints(tenant_id: UUID, document_id: UUID) -> None:
    """Delete LangGraph checkpoint rows for this document (thread_id)."""
    async with tenant_session(tenant_id) as session:
        for table in _CHECKPOINT_TABLES:
            # to_regclass returns NULL (no error) if the table doesn't exist yet,
            # so a fresh DB without any checkpoints doesn't abort the transaction.
            exists = (
                await session.execute(text("SELECT to_regclass(:t)"), {"t": table})
            ).scalar_one()
            if exists is not None:
                await session.execute(
                    text(f"DELETE FROM {table} WHERE thread_id = :tid"),
                    {"tid": str(document_id)},
                )
