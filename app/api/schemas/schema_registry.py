"""Schema-registry (extraction template) request/response schemas."""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.schemas.common import SchemaStatus


class SchemaBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    json_schema: dict[str, Any] = Field(
        ..., description="JSON Schema defining the extraction output structure"
    )
    required_fields: list[str] = Field(default_factory=list)
    pii_fields: list[str] = Field(default_factory=list)
    prompt_template: str | None = None
    confidence_high: float = Field(default=0.85, gt=0.0, le=1.0)
    confidence_medium: float = Field(default=0.60, ge=0.0, lt=1.0)
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_thresholds(self) -> SchemaBase:
        if self.confidence_medium >= self.confidence_high:
            raise ValueError(
                f"confidence_medium ({self.confidence_medium}) must be less than "
                f"confidence_high ({self.confidence_high})"
            )
        return self


class CreateSchemaRequest(SchemaBase):
    pass


class UpdateSchemaStatusRequest(BaseModel):
    status: SchemaStatus


class SchemaResponse(SchemaBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    status: SchemaStatus
    current_version: int
    seed_count: int
    created_at: dt.datetime
    updated_at: dt.datetime


class SchemaVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    schema_id: UUID
    version: int
    json_schema: dict[str, Any]
    required_fields: list[str]
    pii_fields: list[str]
    prompt_template: str | None
    created_at: dt.datetime
