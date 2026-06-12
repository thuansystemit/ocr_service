"""SQLAlchemy 2.0 ORM models mapping to the migration-defined schema (001-004).

These map onto tables created by the raw-SQL migrations; they do not own DDL.
``documents`` and ``review_tasks`` use SQLAlchemy optimistic locking via
``version_id_col`` so a concurrent update raises ``StaleDataError`` (surfaced as
HTTP 409 at the API layer).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_UUID = UUID(as_uuid=True)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID, primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    webhook_url: Mapped[str | None] = mapped_column(Text)
    webhook_secret: Mapped[str] = mapped_column(Text, nullable=False)
    max_queue_size: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    pii_to_llm_policy: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ENCRYPT_BEFORE_LLM"
    )
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID, primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=lambda: ["extract", "read"]
    )
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Schema(Base):
    __tablename__ = "schemas"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_schemas_tenant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID, primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    json_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    required_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    pii_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    prompt_template: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence_high: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0.850)
    confidence_medium: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0.600)
    seed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SchemaVersion(Base):
    __tablename__ = "schema_versions"
    __table_args__ = (
        UniqueConstraint("schema_id", "version", name="uq_schema_versions_schema_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID, primary_key=True, server_default=func.gen_random_uuid()
    )
    schema_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("schemas.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    json_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    required_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    pii_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    prompt_template: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID, primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    schema_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("schemas.id"), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(512))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    file_storage_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    confidence_overall: Mapped[float | None] = mapped_column(Numeric(4, 3))
    routing_decision: Mapped[str | None] = mapped_column(String(10))
    is_dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pipeline_timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012 (SQLAlchemy idiom)


class ExtractionResult(Base):
    __tablename__ = "extraction_results"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID, primary_key=True, server_default=func.gen_random_uuid()
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    extracted_json: Mapped[dict | None] = mapped_column(JSONB)
    extracted_json_hash: Mapped[str | None] = mapped_column(String(64))
    llm_model_used: Mapped[str | None] = mapped_column(String(100))
    llm_token_usage: Mapped[dict | None] = mapped_column(JSONB)
    confidence_overall: Mapped[float | None] = mapped_column(Numeric(4, 3))
    confidence_breakdown: Mapped[dict | None] = mapped_column(JSONB)
    low_confidence_fields: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    missing_fields: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GuardrailReport(Base):
    __tablename__ = "guardrail_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID, primary_key=True, server_default=func.gen_random_uuid()
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    guardrail_name: Mapped[str] = mapped_column(String(100), nullable=False)
    result: Mapped[str] = mapped_column(String(10), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    confidence_multiplier: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, default=1.000
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID, primary_key=True, server_default=func.gen_random_uuid()
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    extraction_result_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("extraction_results.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(_UUID)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(_UUID)
    corrections: Mapped[dict | None] = mapped_column(JSONB)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012 (SQLAlchemy idiom)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID, primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(_UUID, nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(_UUID)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(30))
    payload_hash: Mapped[str | None] = mapped_column(String(64))
    audit_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DeadLetter(Base):
    __tablename__ = "dlq"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID, primary_key=True, server_default=func.gen_random_uuid()
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    failure_reason: Mapped[str] = mapped_column(String(100), nullable=False)
    pipeline_state: Mapped[dict | None] = mapped_column(JSONB)
    last_http_status: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID, primary_key=True, server_default=func.gen_random_uuid()
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


__all__ = [
    "ApiKey",
    "AuditLog",
    "Base",
    "DeadLetter",
    "Document",
    "ExtractionResult",
    "GuardrailReport",
    "ReviewTask",
    "Schema",
    "SchemaVersion",
    "Tenant",
    "WebhookDelivery",
]
