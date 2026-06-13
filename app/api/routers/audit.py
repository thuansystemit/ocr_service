"""Audit export API (T-072, REQ-038).

Streams a tenant's audit trail over a date range as NDJSON or CSV. The response is
streamed row-by-row so a 90-day window doesn't buffer in memory, and it is
RLS-scoped to the caller's tenant.

The streaming generators open their *own* tenant-scoped session, because a
``StreamingResponse`` body is consumed after the route function returns — by which
point a request-scoped dependency session would already be closed.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.context import AuthContext
from app.api.dependencies import require_auth
from app.db.models import AuditLog
from app.db.session import tenant_session

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])

_COLUMNS = ["id", "document_id", "event_type", "actor", "status", "payload_hash", "created_at"]


def _row_values(row: AuditLog) -> dict[str, object]:
    return {
        "id": str(row.id),
        "document_id": str(row.document_id) if row.document_id else None,
        "event_type": row.event_type,
        "actor": row.actor,
        "status": row.status,
        "payload_hash": row.payload_hash,
        "created_at": row.created_at.isoformat(),
    }


def _build_query(start: dt.datetime | None, end: dt.datetime | None) -> Select:
    stmt = select(AuditLog).order_by(AuditLog.created_at)
    if start is not None:
        stmt = stmt.where(AuditLog.created_at >= start)
    if end is not None:
        stmt = stmt.where(AuditLog.created_at <= end)
    return stmt


async def _stream_rows(session: AsyncSession, stmt: Select) -> AsyncIterator[AuditLog]:
    result = await session.stream(stmt)
    async for row in result.scalars():
        yield row


@router.get("/export")
async def export_audit(
    auth: AuthContext = Depends(require_auth),
    fmt: str = Query(default="ndjson", alias="format", pattern="^(ndjson|csv)$"),
    start: dt.datetime | None = Query(default=None),
    end: dt.datetime | None = Query(default=None),
) -> StreamingResponse:
    stmt = _build_query(start, end)
    tenant_id = auth.tenant_id

    async def ndjson() -> AsyncIterator[bytes]:
        async with tenant_session(tenant_id) as session:
            async for row in _stream_rows(session, stmt):
                yield (json.dumps(_row_values(row)) + "\n").encode()

    async def csv_rows() -> AsyncIterator[bytes]:
        header = io.StringIO()
        csv.writer(header).writerow(_COLUMNS)
        yield header.getvalue().encode()
        async with tenant_session(tenant_id) as session:
            async for row in _stream_rows(session, stmt):
                buf = io.StringIO()
                csv.writer(buf).writerow([_row_values(row)[c] for c in _COLUMNS])
                yield buf.getvalue().encode()

    if fmt == "csv":
        return StreamingResponse(csv_rows(), media_type="text/csv")
    return StreamingResponse(ndjson(), media_type="application/x-ndjson")
