"""Pipeline runner (C-17 → C-10 bridge).

``enqueue_pipeline`` schedules a document for async processing; ``run_pipeline``
loads it, runs the checkpointed LangGraph, persists the terminal outcome, and
releases the tenant's rate-limit slot. In Sprint 3 the API process runs the
pipeline in-loop (``asyncio.create_task``); a dedicated worker consuming a durable
queue is a later refinement.
"""

from __future__ import annotations

import asyncio
from typing import cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DeadLetter, Document, ExtractionResult, ReviewTask, Schema
from app.db.session import tenant_session
from app.observability.logging import bind_context, get_logger
from app.pipeline.checkpoint import checkpointed_graph
from app.pipeline.state import ExtractionState
from app.services.rate_limit import get_rate_limiter
from app.worker.pool import get_worker_pool

log = get_logger(__name__)

_background_tasks: set[asyncio.Task] = set()

_TERMINAL = {"completed", "review", "rejected", "error", "cancelled"}


def enqueue_pipeline(document_id: UUID, tenant_id: UUID) -> None:
    """Fire-and-forget schedule of a pipeline run (keeps a task ref so it is not GC'd)."""
    task = asyncio.create_task(run_pipeline(document_id, tenant_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def run_pipeline(document_id: UUID, tenant_id: UUID) -> None:
    pool = get_worker_pool()
    try:
        await pool.submit(
            tenant_id,
            lambda: _process(document_id, tenant_id),
            document_id=str(document_id),
        )
    finally:
        await get_rate_limiter().release(tenant_id)


async def _process(document_id: UUID, tenant_id: UUID) -> None:
    bind_context(tenant_id=str(tenant_id), document_id=str(document_id))
    initial = await _load_initial_state(document_id, tenant_id)
    if initial is None:
        log.warning("pipeline.document_missing")
        return

    config: RunnableConfig = {"configurable": {"thread_id": str(document_id)}}
    async with checkpointed_graph() as graph:
        final = cast(ExtractionState, await graph.ainvoke(initial, config))

    await _persist_outcome(document_id, tenant_id, final)
    log.info(
        "pipeline.completed", status=final.get("status"), routing=final.get("routing_decision")
    )


async def _load_initial_state(document_id: UUID, tenant_id: UUID) -> ExtractionState | None:
    async with tenant_session(tenant_id) as session:
        document = await session.get(Document, document_id)
        if document is None:
            return None
        schema = await session.get(Schema, document.schema_id)
        state: ExtractionState = {
            "document_id": str(document_id),
            "tenant_id": str(tenant_id),
            "schema_id": str(document.schema_id),
            "schema_version": document.schema_version,
            "schema_name": schema.name if schema else "",
            "file_storage_key": document.file_storage_key or "",
            "confidence_high": float(schema.confidence_high) if schema else 0.85,
            "confidence_medium": float(schema.confidence_medium) if schema else 0.60,
            "json_schema": dict(schema.json_schema) if schema else {},
            "required_fields": list(schema.required_fields) if schema else [],
            "pii_fields": list(schema.pii_fields) if schema else [],
            "status": "pending",
            "is_cancelled": False,
        }
        return state


async def _persist_outcome(document_id: UUID, tenant_id: UUID, state: ExtractionState) -> None:
    final_status = state.get("status", "error")
    confidence = state.get("confidence")
    async with tenant_session(tenant_id) as session:
        document = await session.get(Document, document_id)
        if document is None:
            return
        document.status = final_status if final_status in _TERMINAL else "error"
        document.routing_decision = state.get("routing_decision")
        if confidence is not None:
            document.confidence_overall = confidence

        if final_status in ("completed", "review"):
            await _write_extraction_result(session, document_id, tenant_id, state, final_status)
        elif final_status in ("rejected", "error"):
            session.add(
                DeadLetter(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    failure_reason=state.get("failure_reason") or "UNKNOWN",
                    pipeline_state=_snapshot(state),
                    status="pending",
                )
            )


async def _write_extraction_result(
    session: AsyncSession,
    document_id: UUID,
    tenant_id: UUID,
    state: ExtractionState,
    final_status: str,
) -> None:
    extracted = state.get("extracted_json") or {}
    pii_fields = state.get("pii_fields") or []
    if pii_fields:  # encrypt PII at rest (C-08); no-op + no key needed when empty
        from app.domain.encryption import encrypt_fields

        extracted = encrypt_fields(extracted, pii_fields, tenant_id)

    result = ExtractionResult(
        document_id=document_id,
        tenant_id=tenant_id,
        extracted_json=extracted,
        llm_model_used=state.get("llm_model_used"),
        llm_token_usage=state.get("llm_token_usage"),
        confidence_overall=state.get("confidence"),
        confidence_breakdown=state.get("confidence_breakdown"),
        low_confidence_fields=state.get("low_confidence_fields"),
        missing_fields=state.get("missing_fields"),
    )
    session.add(result)
    await session.flush()
    if final_status == "review":
        session.add(
            ReviewTask(
                document_id=document_id,
                tenant_id=tenant_id,
                extraction_result_id=result.id,
                status="pending",
            )
        )


def _snapshot(state: ExtractionState) -> dict:
    """A JSON-safe subset of state for the DLQ row (no raw document text)."""
    return {
        k: state.get(k)
        for k in (
            "current_step",
            "routing_decision",
            "confidence",
            "failure_reason",
            "error",
            "parse_method",
        )
        if state.get(k) is not None
    }
