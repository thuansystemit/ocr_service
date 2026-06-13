"""Dead-letter queue response schema."""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DlqResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    failure_reason: str
    last_http_status: int | None
    status: str
    retry_count: int
    created_at: dt.datetime
    updated_at: dt.datetime
