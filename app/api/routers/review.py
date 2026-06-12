"""Human review queue endpoints (T-064, US-002).

Lists documents that landed in MEDIUM confidence (a ``review_tasks`` row is
created only for those) and exposes one for inspection alongside its extracted
fields. Review *actions* (accept/correct/reject) are Sprint 6 (T-065). All
queries are RLS-scoped to the caller's tenant.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.api.schemas.document import ExtractionResultResponse, ReviewTaskResponse
from app.db.models import ExtractionResult, ReviewTask

router = APIRouter(prefix="/api/v1/review", tags=["review"])

_OPEN_STATUSES = ("pending", "in_progress")


@router.get("", response_model=list[ReviewTaskResponse])
async def list_review_queue(
    session: AsyncSession = Depends(get_session),
) -> list[ReviewTaskResponse]:
    rows = await session.execute(
        select(ReviewTask)
        .where(ReviewTask.status.in_(_OPEN_STATUSES))
        .order_by(ReviewTask.created_at)
    )
    return [ReviewTaskResponse.model_validate(r) for r in rows.scalars().all()]


@router.get("/{review_id}")
async def get_review(
    review_id: UUID, session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    review = await session.get(ReviewTask, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "review task not found")
    extraction = await session.get(ExtractionResult, review.extraction_result_id)
    return {
        "review": ReviewTaskResponse.model_validate(review).model_dump(mode="json"),
        "document_id": str(review.document_id),
        "extraction": (
            ExtractionResultResponse.model_validate(extraction).model_dump(mode="json")
            if extraction
            else None
        ),
    }
