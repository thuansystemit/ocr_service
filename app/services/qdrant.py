"""Qdrant vector service (C-18) -- the cross-tenant leakage guard (EC-001/002).

This is the single most security-critical component in the RAG path. Three rules,
all enforced here so no caller can bypass them:

1. **Mandatory tenant filter.** Every search must pass a ``tenant_id``; a missing
   one raises ``TenantFilterMissingError`` (a hard reject, never a silent
   unscoped query).
2. **Post-query assertion.** Every returned point's ``payload.tenant_id`` is
   checked against the requesting tenant; any mismatch logs CRITICAL and the
   whole result is discarded by raising.
3. **Tenant-prefixed everything.** Upserts always stamp ``tenant_id`` into the
   payload and the indexed filter fields.

The Qdrant client is injectable so tests exercise the guard with a fake.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.observability.logging import get_logger

log = get_logger(__name__)


class TenantFilterMissingError(Exception):
    """Raised when a vector query is attempted without a tenant_id filter."""


class CrossTenantLeakageError(Exception):
    """Raised when Qdrant returns a point belonging to a different tenant."""


class QdrantService:
    def __init__(self, client: Any | None = None, collection: str | None = None) -> None:
        self._client = client
        self._collection = collection or get_settings().qdrant_collection

    def _ensure_client(self) -> Any:
        if self._client is None:
            from qdrant_client import AsyncQdrantClient

            settings = get_settings()
            api_key = (
                settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
            )
            self._client = AsyncQdrantClient(url=settings.qdrant_url, api_key=api_key)
        return self._client

    async def upsert_example(
        self,
        *,
        tenant_id: uuid.UUID | str,
        schema_id: uuid.UUID | str,
        document_id: uuid.UUID | str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        from qdrant_client import models

        full_payload = {
            **payload,
            "tenant_id": str(tenant_id),
            "schema_id": str(schema_id),
            "document_id": str(document_id),
        }
        point = models.PointStruct(id=str(uuid.uuid4()), vector=vector, payload=full_payload)
        await self._ensure_client().upsert(collection_name=self._collection, points=[point])

    async def delete_by_document(
        self, *, tenant_id: uuid.UUID | str, document_id: uuid.UUID | str
    ) -> None:
        """Delete all vectors for a document (GDPR erasure / retention).

        Filtered by both tenant_id and document_id so a wrong document_id can
        never delete another tenant's vectors.
        """
        if not tenant_id:
            raise TenantFilterMissingError("tenant_id is required to delete vectors")
        from qdrant_client import models

        await self._ensure_client().delete(
            collection_name=self._collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="tenant_id", match=models.MatchValue(value=str(tenant_id))
                        ),
                        models.FieldCondition(
                            key="document_id", match=models.MatchValue(value=str(document_id))
                        ),
                    ]
                )
            ),
        )

    async def search(
        self,
        *,
        tenant_id: uuid.UUID | str,
        schema_id: uuid.UUID | str,
        vector: list[float],
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        if not tenant_id:
            raise TenantFilterMissingError("tenant_id is required for every Qdrant query")

        from qdrant_client import models

        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="tenant_id", match=models.MatchValue(value=str(tenant_id))
                ),
                models.FieldCondition(
                    key="schema_id", match=models.MatchValue(value=str(schema_id))
                ),
            ]
        )
        response = await self._ensure_client().query_points(
            collection_name=self._collection,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )

        payloads: list[dict[str, Any]] = []
        for point in response.points:
            payload = point.payload or {}
            if str(payload.get("tenant_id")) != str(tenant_id):
                log.critical(
                    "qdrant.cross_tenant_leak",
                    requested_tenant=str(tenant_id),
                    returned_tenant=payload.get("tenant_id"),
                )
                raise CrossTenantLeakageError("Qdrant returned a point for a different tenant")
            payloads.append(payload)
        return payloads


_service: QdrantService | None = None


def get_qdrant_service() -> QdrantService:
    global _service
    if _service is None:
        _service = QdrantService()
    return _service


def set_qdrant_service(service: QdrantService | None) -> None:
    """Override the process Qdrant service (tests; pass None to reset)."""
    global _service
    _service = service
