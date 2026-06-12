"""Identity introspection endpoint.

Minimal authenticated route used to confirm the auth + tenant-context chain end
to end. Returns who the caller is and a tenant-scoped count proving RLS is active
through the request path.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.context import AuthContext
from app.api.dependencies import get_session, require_auth

router = APIRouter(prefix="/api/v1", tags=["identity"])


@router.get("/me")
async def me(auth: AuthContext = Depends(require_auth)) -> dict[str, object]:
    return {
        "tenant_id": str(auth.tenant_id),
        "principal": auth.principal,
        "scopes": list(auth.scopes),
    }


@router.get("/me/schemas/count")
async def my_schema_count(
    auth: AuthContext = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    # RLS restricts this COUNT to the caller's tenant automatically.
    count = (await session.execute(text("SELECT count(*) FROM schemas"))).scalar_one()
    return {"tenant_id": str(auth.tenant_id), "schema_count": count}
