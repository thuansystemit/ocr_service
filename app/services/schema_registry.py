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
from app.db.models import Schema, SchemaVersion


class SchemaNotFoundError(Exception):
    pass


class DuplicateSchemaError(Exception):
    pass


class ActivationError(Exception):
    """Raised when a schema cannot be activated (e.g. too few seed examples)."""


MIN_SEEDS_FOR_ACTIVATION = 3


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


async def add_seed_example(
    session: AsyncSession,
    schema_id: UUID,
    *,
    tenant_id: UUID,
    input_text: str,
    expected_json: dict,
) -> Schema:
    """Store a labelled few-shot example in Qdrant and bump ``seed_count`` (T-028).

    The example is embedded and upserted tenant-scoped so it can later be
    retrieved as a few-shot for this schema's extractions.
    """
    from app.domain.embeddings import get_embedder
    from app.services.qdrant import get_qdrant_service

    schema = await get_schema(session, schema_id)
    vector = await get_embedder().embed(input_text[:8000])
    await get_qdrant_service().upsert_example(
        tenant_id=tenant_id,
        schema_id=schema_id,
        document_id=schema_id,  # seeds are keyed to the schema, not a document
        vector=vector,
        payload={
            "schema_name": schema.name,
            "source": "seed",
            "input_text": input_text[:2000],
            "expected_json": expected_json,
        },
    )
    schema.seed_count += 1
    await session.flush()
    return schema


async def activate_schema(session: AsyncSession, schema_id: UUID) -> Schema:
    """Activate a draft schema (T-027/029).

    Gated on ``seed_count >= 3`` (REQ-026). Each activation snapshots the current
    definition into ``schema_versions`` and bumps ``current_version`` so in-flight
    documents keep their pinned contract.
    """
    schema = await get_schema(session, schema_id)
    if schema.seed_count < MIN_SEEDS_FOR_ACTIVATION:
        raise ActivationError(
            f"activation requires >= {MIN_SEEDS_FOR_ACTIVATION} seed examples "
            f"(has {schema.seed_count})"
        )
    if schema.status != "active":
        schema.current_version += 1 if schema.status == "deprecated" else 0
    session.add(
        SchemaVersion(
            schema_id=schema.id,
            tenant_id=schema.tenant_id,
            version=schema.current_version,
            json_schema=schema.json_schema,
            required_fields=schema.required_fields,
            pii_fields=schema.pii_fields,
            prompt_template=schema.prompt_template,
        )
    )
    schema.status = "active"
    await session.flush()
    return schema
