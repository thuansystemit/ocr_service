"""Review action service (T-065/066, REQ-016/017/019).

Handles the human decision on a MEDIUM-confidence document:

* **accept**  — the extraction is correct as-is.
* **correct** — the reviewer supplies field corrections; the corrected record is
  what gets delivered, and a *corrected* few-shot example is written back to
  Qdrant so future similar documents extract better (active learning).
* **reject**  — the extraction is unusable.

Optimistic locking on ``review_tasks.version`` (the SQLAlchemy mapper raises
``StaleDataError`` on a stale write) means two reviewers acting on the same task
don't clobber each other — the second gets a 409.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, ExtractionResult, ReviewTask
from app.observability.logging import get_logger
from app.services import audit

log = get_logger(__name__)


class ReviewNotFoundError(Exception):
    pass


class InvalidReviewActionError(Exception):
    pass


async def apply_action(
    session: AsyncSession,
    review_id: UUID,
    *,
    tenant_id: UUID,
    action: str,
    expected_version: int,
    corrections: dict[str, dict[str, Any]] | None = None,
    rejection_reason: str | None = None,
) -> ReviewTask:
    review = await session.get(ReviewTask, review_id)
    if review is None:
        raise ReviewNotFoundError(f"review task {review_id} not found")
    if review.version != expected_version:
        # Surfaced as 409 at the API layer (optimistic-lock conflict).
        raise InvalidReviewActionError(
            f"version mismatch: expected {review.version}, got {expected_version}"
        )

    if action == "accept":
        review.status = "accepted"
    elif action == "correct":
        if not corrections:
            raise InvalidReviewActionError("corrections required for 'correct'")
        review.status = "corrected"
        review.corrections = corrections
        await _apply_corrections(session, review, corrections, tenant_id)
    elif action == "reject":
        review.status = "rejected"
        review.rejection_reason = rejection_reason
    else:
        raise InvalidReviewActionError(f"unknown action: {action}")

    document = await session.get(Document, review.document_id)
    if document is not None:
        document.status = "rejected" if action == "reject" else "completed"

    await audit.append_event(
        session,
        tenant_id=tenant_id,
        document_id=review.document_id,
        event_type=f"REVIEW_{action.upper()}",
        actor="reviewer",
        status=review.status,
        metadata={"review_id": str(review_id)},
    )
    await session.flush()
    return review


async def _apply_corrections(
    session: AsyncSession,
    review: ReviewTask,
    corrections: dict[str, dict[str, Any]],
    tenant_id: UUID,
) -> None:
    """Apply ``{field: {new: value}}`` corrections to the stored extraction and
    write a corrected few-shot example back to Qdrant (active learning)."""
    extraction = await session.get(ExtractionResult, review.extraction_result_id)
    if extraction is None or extraction.extracted_json is None:
        return
    corrected = dict(extraction.extracted_json)
    for field, change in corrections.items():
        if "new" in change:
            corrected[field] = change["new"]
    extraction.extracted_json = corrected

    # Best-effort few-shot write-back; never fail the review on a vector-store error.
    try:
        from app.domain.embeddings import get_embedder
        from app.services.qdrant import get_qdrant_service

        document = await session.get(Document, review.document_id)
        vector = await get_embedder().embed(str(corrected)[:8000])
        await get_qdrant_service().upsert_example(
            tenant_id=tenant_id,
            schema_id=document.schema_id if document else review.document_id,
            document_id=review.document_id,
            vector=vector,
            payload={"source": "correction", "expected_json": corrected},
        )
    except Exception as exc:
        log.warning("review.fewshot_writeback_failed", error=str(exc))


async def count_stale_reviews(session: AsyncSession, *, older_than_hours: int = 24) -> int:
    """Count pending review tasks older than the SLA (T-067 stale notification)."""
    from sqlalchemy import func, select

    stmt = (
        select(func.count())
        .select_from(ReviewTask)
        .where(
            ReviewTask.status.in_(("pending", "in_progress")),
            ReviewTask.created_at < func.now() - func.make_interval(0, 0, 0, 0, older_than_hours),
        )
    )
    return (await session.execute(stmt)).scalar_one()
