"""Document / extraction / guardrail / review response schemas.

Kept in one module so the nested forward references on ``DocumentDetailResponse``
resolve without circular imports.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.schemas.common import (
    DocumentStatus,
    GuardrailResultValue,
    ReviewStatus,
    RoutingDecision,
)


class ExtractRequest(BaseModel):
    """Non-file fields of ``POST /api/v1/extract`` (multipart)."""

    schema_name: str = Field(..., min_length=1, max_length=255)
    dry_run: bool = False
    callback_url: str | None = None  # overrides tenant default webhook_url


class ConfidenceBreakdown(BaseModel):
    llm: float = Field(..., ge=0.0, le=1.0)
    completeness: float = Field(..., ge=0.0, le=1.0)
    semantic: float = Field(..., ge=0.0, le=1.0)
    guardrail_adjusted: float = Field(..., ge=0.0, le=1.0)


class ExtractionResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    extracted_json: dict[str, Any] | None
    extracted_json_hash: str | None
    llm_model_used: str | None
    llm_token_usage: dict[str, int] | None
    confidence_overall: float | None
    confidence_breakdown: ConfidenceBreakdown | None
    low_confidence_fields: list[str] | None = None
    missing_fields: list[str] | None = None
    created_at: dt.datetime


class GuardrailReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    guardrail_name: str
    result: GuardrailResultValue
    detail: str | None
    confidence_multiplier: float
    created_at: dt.datetime


class ReviewTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    extraction_result_id: UUID
    status: ReviewStatus
    assigned_to: UUID | None
    reviewer_id: UUID | None
    corrections: dict[str, Any] | None
    rejection_reason: str | None
    version: int
    created_at: dt.datetime
    updated_at: dt.datetime


class ReviewActionRequest(BaseModel):
    action: str = Field(..., pattern=r"^(accept|correct|reject)$")
    corrections: dict[str, dict[str, Any]] | None = None  # {field: {old, new}}
    rejection_reason: str | None = None
    version: int = Field(..., description="Current version for optimistic locking")

    @model_validator(mode="after")
    def validate_action_fields(self) -> ReviewActionRequest:
        if self.action == "correct" and not self.corrections:
            raise ValueError("corrections required when action is correct")
        if self.action == "reject" and not self.rejection_reason:
            raise ValueError("rejection_reason required when action is reject")
        return self


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    schema_id: UUID
    schema_version: int
    file_name: str | None
    file_size_bytes: int | None
    mime_type: str | None
    status: DocumentStatus
    confidence_overall: float | None
    routing_decision: RoutingDecision | None
    is_dry_run: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class DocumentDetailResponse(DocumentResponse):
    extraction_result: ExtractionResultResponse | None = None
    guardrail_reports: list[GuardrailReportResponse] = []
    review_task: ReviewTaskResponse | None = None
