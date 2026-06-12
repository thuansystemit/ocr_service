"""Schema-registry service (T-026): tenant-scoped CRUD over extraction schemas.

All queries run on the caller's tenant-scoped session, so RLS guarantees a tenant
only ever sees or mutates its own schemas. Schema *activation* (draft -> active)
and versioning land in Sprint 6 (T-027); creation here always yields a ``draft``.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.schema_registry import CreateSchemaRequest
from app.db.models import Schema


class SchemaNotFoundError(Exception):
    pass


class DuplicateSchemaError(Exception):
    pass


async def create_schema(
    session: AsyncSession, tenant_id: UUID, payload: CreateSchemaRequest
) -> Schema:
    existing = (
        await session.execute(select(Schema).where(Schema.name == payload.name))
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateSchemaError(f"schema {payload.name!r} already exists")

    schema = Schema(
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        json_schema=payload.json_schema,
        required_fields=payload.required_fields,
        pii_fields=payload.pii_fields,
        prompt_template=payload.prompt_template,
        confidence_high=payload.confidence_high,
        confidence_medium=payload.confidence_medium,
        config=payload.config,
        status="draft",
        current_version=1,
    )
    session.add(schema)
    await session.flush()
    return schema


async def get_schema(session: AsyncSession, schema_id: UUID) -> Schema:
    schema = await session.get(Schema, schema_id)
    if schema is None:
        raise SchemaNotFoundError(f"schema {schema_id} not found")
    return schema


async def list_schemas(session: AsyncSession) -> list[Schema]:
    rows = await session.execute(select(Schema).order_by(Schema.created_at.desc()))
    return list(rows.scalars().all())


async def update_schema(
    session: AsyncSession, schema_id: UUID, payload: CreateSchemaRequest
) -> Schema:
    schema = await get_schema(session, schema_id)
    schema.description = payload.description
    schema.json_schema = payload.json_schema
    schema.required_fields = payload.required_fields
    schema.pii_fields = payload.pii_fields
    schema.prompt_template = payload.prompt_template
    schema.confidence_high = payload.confidence_high
    schema.confidence_medium = payload.confidence_medium
    schema.config = payload.config
    await session.flush()
    return schema
