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
from sqlalchemy.orm.exc import StaleDataError

from app.api.context import get_current_tenant
from app.api.dependencies import get_session
from app.api.schemas.document import (
    ExtractionResultResponse,
    ReviewActionRequest,
    ReviewTaskResponse,
)
from app.db.models import ExtractionResult, ReviewTask
from app.services import review as review_svc

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


@router.post("/{review_id}", response_model=ReviewTaskResponse)
async def act_on_review(
    review_id: UUID,
    payload: ReviewActionRequest,
    session: AsyncSession = Depends(get_session),
) -> ReviewTaskResponse:
    tenant = get_current_tenant()
    if tenant is None:  # pragma: no cover - get_session always sets it
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no tenant context")
    try:
        review = await review_svc.apply_action(
            session,
            review_id,
            tenant_id=UUID(tenant),
            action=payload.action,
            expected_version=payload.version,
            corrections=payload.corrections,
            rejection_reason=payload.rejection_reason,
        )
    except review_svc.ReviewNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except review_svc.InvalidReviewActionError as exc:
        # version mismatch / bad action -> 409 conflict (optimistic lock, REQ-019)
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except StaleDataError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "review was modified concurrently") from exc
    return ReviewTaskResponse.model_validate(review)
