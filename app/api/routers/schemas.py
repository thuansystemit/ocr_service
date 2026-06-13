"""Schema-registry CRUD endpoints (T-026, US-003)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.api.schemas.schema_registry import (
    CreateSchemaRequest,
    SchemaResponse,
    SeedExampleRequest,
)
from app.services import schema_registry as svc

router = APIRouter(prefix="/api/v1/schemas", tags=["schemas"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SchemaResponse)
async def create_schema(
    payload: CreateSchemaRequest,
    session: AsyncSession = Depends(get_session),
) -> SchemaResponse:
    try:
        schema = await svc.create_schema(session, _tenant(), payload)
    except svc.DuplicateSchemaError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.flush()
    return SchemaResponse.model_validate(schema)


@router.get("", response_model=list[SchemaResponse])
async def list_schemas(session: AsyncSession = Depends(get_session)) -> list[SchemaResponse]:
    schemas = await svc.list_schemas(session)
    return [SchemaResponse.model_validate(s) for s in schemas]


@router.get("/{schema_id}", response_model=SchemaResponse)
async def get_schema(
    schema_id: UUID, session: AsyncSession = Depends(get_session)
) -> SchemaResponse:
    try:
        schema = await svc.get_schema(session, schema_id)
    except svc.SchemaNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return SchemaResponse.model_validate(schema)


@router.put("/{schema_id}", response_model=SchemaResponse)
async def update_schema(
    schema_id: UUID,
    payload: CreateSchemaRequest,
    session: AsyncSession = Depends(get_session),
) -> SchemaResponse:
    try:
        schema = await svc.update_schema(session, schema_id, payload)
    except svc.SchemaNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return SchemaResponse.model_validate(schema)


@router.post("/{schema_id}/seeds", response_model=SchemaResponse)
async def add_seed(
    schema_id: UUID,
    payload: SeedExampleRequest,
    session: AsyncSession = Depends(get_session),
) -> SchemaResponse:
    try:
        schema = await svc.add_seed_example(
            session,
            schema_id,
            tenant_id=_tenant(),
            input_text=payload.input_text,
            expected_json=payload.expected_json,
        )
    except svc.SchemaNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return SchemaResponse.model_validate(schema)


@router.post("/{schema_id}/activate", response_model=SchemaResponse)
async def activate_schema(
    schema_id: UUID, session: AsyncSession = Depends(get_session)
) -> SchemaResponse:
    try:
        schema = await svc.activate_schema(session, schema_id)
    except svc.SchemaNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except svc.ActivationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return SchemaResponse.model_validate(schema)


def _tenant() -> UUID:
    """Read the tenant id bound to the request context."""
    from app.api.context import get_current_tenant

    tenant = get_current_tenant()
    if tenant is None:  # pragma: no cover - get_session always sets it
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no tenant context")
    return UUID(tenant)
