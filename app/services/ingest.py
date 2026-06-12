"""Ingest service (T-021/023/024): validate, store, persist, enqueue.

Creates a ``documents`` row in ``pending`` and hands the id to the pipeline. The
file bytes go to blob storage; only a ``file_storage_key`` is kept in the row.
The active schema is resolved by name within the caller's tenant (RLS-scoped) and
its ``current_version`` is pinned onto the document so later schema edits do not
change an in-flight document's contract (REQ-025).
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Document, Schema
from app.domain.storage import get_storage
from app.observability.logging import get_logger

log = get_logger(__name__)


class IngestError(Exception):
    """Base class for ingest validation failures."""


class FileTooLargeError(IngestError):
    pass


class UnsupportedMediaTypeError(IngestError):
    pass


class UnknownSchemaError(IngestError):
    pass


class EmptyFileError(IngestError):
    pass


def validate_upload(content: bytes, mime_type: str | None) -> None:
    settings = get_settings()
    if not content:
        raise EmptyFileError("uploaded file is empty")
    if len(content) > settings.max_file_size_bytes:
        raise FileTooLargeError(
            f"file is {len(content)} bytes; limit is {settings.max_file_size_bytes}"
        )
    if mime_type not in settings.allowed_mime_types:
        raise UnsupportedMediaTypeError(f"unsupported MIME type: {mime_type!r}")


async def _resolve_active_schema(session: AsyncSession, schema_name: str) -> Schema:
    schema = (
        await session.execute(
            select(Schema).where(Schema.name == schema_name, Schema.status == "active")
        )
    ).scalar_one_or_none()
    if schema is None:
        raise UnknownSchemaError(f"no active schema named {schema_name!r}")
    return schema


async def create_document(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    schema_name: str,
    file_name: str | None,
    content: bytes,
    mime_type: str | None,
    is_dry_run: bool = False,
) -> Document:
    """Validate, store the blob, and persist a ``pending`` document row.

    Runs inside the caller's tenant-scoped session/transaction, so RLS applies to
    both the schema lookup and the insert.
    """
    validate_upload(content, mime_type)
    schema = await _resolve_active_schema(session, schema_name)

    document = Document(
        tenant_id=tenant_id,
        schema_id=schema.id,
        schema_version=schema.current_version,
        file_name=file_name,
        file_size_bytes=len(content),
        mime_type=mime_type,
        status="pending",
        is_dry_run=is_dry_run,
    )
    session.add(document)
    await session.flush()  # assigns document.id

    storage_key = await get_storage().save(tenant_id, document.id, content)
    document.file_storage_key = storage_key

    log.info(
        "ingest.document_created",
        document_id=str(document.id),
        schema=schema_name,
        size_bytes=len(content),
        checksum=hashlib.sha256(content).hexdigest()[:16],
        dry_run=is_dry_run,
    )
    return document
