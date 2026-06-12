"""Tenant request/response schemas."""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.common import PiiToLlmPolicy


class TenantBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")
    webhook_url: str | None = None
    max_queue_size: int = Field(default=500, ge=1, le=10000)
    retention_days: int = Field(default=90, ge=1, le=3650)
    pii_to_llm_policy: PiiToLlmPolicy = PiiToLlmPolicy.ENCRYPT_BEFORE_LLM
    config: dict[str, Any] = Field(default_factory=dict)


class CreateTenantRequest(TenantBase):
    webhook_secret: str = Field(..., min_length=16, max_length=256)


class TenantResponse(TenantBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: dt.datetime
    updated_at: dt.datetime
