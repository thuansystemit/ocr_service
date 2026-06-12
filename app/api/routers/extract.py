"""Ingest + document-status endpoints (C-02).

``POST /api/v1/extract`` validates and persists an uploaded document, enqueues it
to the pipeline, and returns ``202`` with the ``document_id`` -- the heavy work
happens asynchronously. ``GET /api/v1/documents/{id}`` returns current status and
results (RLS-scoped to the caller's tenant).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.context import AuthContext
from app.api.dependencies import get_session, require_auth
from app.api.schemas.document import (
    DocumentDetailResponse,
    ExtractionResultResponse,
    GuardrailReportResponse,
    ReviewTaskResponse,
)
from app.db.models import Document, ExtractionResult, GuardrailReport, ReviewTask, Tenant
from app.db.session import tenant_session
from app.services.ingest import (
    EmptyFileError,
    FileTooLargeError,
    UnknownSchemaError,
    UnsupportedMediaTypeError,
    create_document,
)
from app.services.rate_limit import QueueFullError, get_rate_limiter

router = APIRouter(prefix="/api/v1", tags=["extract"])


@router.post("/extract", status_code=status.HTTP_202_ACCEPTED)
async def extract(
    auth: AuthContext = Depends(require_auth),
    file: UploadFile = File(...),
    schema_name: str = Form(...),
    dry_run: bool = Form(False),
) -> dict[str, str]:
    content = await file.read()
    limiter = get_rate_limiter()

    async with tenant_session(auth.tenant_id) as session:
        tenant = await session.get(Tenant, auth.tenant_id)
        max_queue = tenant.max_queue_size if tenant else 500

    try:
        await limiter.acquire(auth.tenant_id, max_queue)
    except QueueFullError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="tenant queue is full",
            headers={"Retry-After": str(exc.retry_after_s)},
        ) from exc

    try:
        async with tenant_session(auth.tenant_id) as session:
            document = await create_document(
                session,
                tenant_id=auth.tenant_id,
                schema_name=schema_name,
                file_name=file.filename,
                content=content,
                mime_type=file.content_type,
                is_dry_run=dry_run,
            )
            document_id = document.id
    except FileTooLargeError as exc:
        await limiter.release(auth.tenant_id)
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc)) from exc
    except (UnsupportedMediaTypeError, UnknownSchemaError, EmptyFileError) as exc:
        await limiter.release(auth.tenant_id)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except Exception:
        await limiter.release(auth.tenant_id)
        raise

    # Enqueue asynchronously; the runner releases the rate-limit slot when done.
    from app.worker.runner import enqueue_pipeline

    enqueue_pipeline(document_id, auth.tenant_id)
    return {"document_id": str(document_id), "status": "pending"}


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> DocumentDetailResponse:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")

    extraction = (
        await session.execute(
            select(ExtractionResult).where(ExtractionResult.document_id == document_id)
        )
    ).scalar_one_or_none()
    guardrails = list(
        (
            await session.execute(
                select(GuardrailReport).where(GuardrailReport.document_id == document_id)
            )
        )
        .scalars()
        .all()
    )
    review = (
        await session.execute(select(ReviewTask).where(ReviewTask.document_id == document_id))
    ).scalar_one_or_none()

    detail = DocumentDetailResponse.model_validate(document)
    detail.extraction_result = (
        ExtractionResultResponse.model_validate(extraction) if extraction else None
    )
    detail.guardrail_reports = [GuardrailReportResponse.model_validate(g) for g in guardrails]
    detail.review_task = ReviewTaskResponse.model_validate(review) if review else None
    return detail
