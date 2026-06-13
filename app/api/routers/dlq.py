"""Dead-letter queue API (T-059/060/061, REQ-044/045/050).

List/inspect failed documents and retry them. Retry is idempotent: a DLQ entry
that is not ``pending`` (already retrying/resolved) returns 409 rather than
re-enqueueing the same document twice.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.api.schemas.dlq import DlqResponse
from app.db.models import DeadLetter, Document

router = APIRouter(prefix="/api/v1/dlq", tags=["dlq"])


@router.get("", response_model=list[DlqResponse])
async def list_dlq(
    session: AsyncSession = Depends(get_session),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[DlqResponse]:
    stmt = select(DeadLetter).order_by(DeadLetter.created_at.desc()).limit(limit).offset(offset)
    if status_filter:
        stmt = stmt.where(DeadLetter.status == status_filter)
    rows = await session.execute(stmt)
    return [DlqResponse.model_validate(r) for r in rows.scalars().all()]


@router.get("/{dlq_id}", response_model=DlqResponse)
async def get_dlq(dlq_id: UUID, session: AsyncSession = Depends(get_session)) -> DlqResponse:
    entry = await session.get(DeadLetter, dlq_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "DLQ entry not found")
    return DlqResponse.model_validate(entry)


@router.post("/{dlq_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_dlq(dlq_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    entry = await session.get(DeadLetter, dlq_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "DLQ entry not found")
    if entry.status != "pending":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"DLQ entry is '{entry.status}', not retryable"
        )

    entry.status = "retrying"
    entry.retry_count += 1
    document = await session.get(Document, entry.document_id)
    if document is not None:
        document.status = "pending"
    tenant_id = entry.tenant_id
    document_id = entry.document_id

    # Re-enter the pipeline after this transaction commits.
    from app.worker.runner import enqueue_pipeline

    enqueue_pipeline(document_id, tenant_id)
    return {"document_id": str(document_id), "status": "retrying"}
