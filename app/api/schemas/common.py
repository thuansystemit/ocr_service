"""Shared enums and base types for API schemas.

The enum values are the canonical strings persisted in the database (they match
the CHECK constraints in migration 001), so they are safe to use directly in
queries and responses.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class PiiToLlmPolicy(str, Enum):
    ENCRYPT_BEFORE_LLM = "ENCRYPT_BEFORE_LLM"
    REDACT_BEFORE_LLM = "REDACT_BEFORE_LLM"
    ALLOW_PLAINTEXT = "ALLOW_PLAINTEXT"


class SchemaStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    GUARDING = "guarding"
    EXTRACTING = "extracting"
    SCORING = "scoring"
    ROUTING = "routing"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    REVIEW = "review"
    REJECTED = "rejected"
    ERROR = "error"
    CANCELLED = "cancelled"
    TOMBSTONE = "tombstone"


class RoutingDecision(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class GuardrailResultValue(str, Enum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class DlqStatus(str, Enum):
    PENDING = "pending"
    RETRYING = "retrying"
    RESOLVED = "resolved"
    EXPIRED = "expired"


class FailureReason(str, Enum):
    PARSE_FAILED = "PARSE_FAILED"
    PARSE_EMPTY_OUTPUT = "PARSE_EMPTY_OUTPUT"
    GUARDRAIL_BLOCK = "GUARDRAIL_BLOCK"
    INJECTION_DETECTED = "INJECTION_DETECTED"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    PIPELINE_TIMEOUT = "PIPELINE_TIMEOUT"
    WEBHOOK_DELIVERY_FAILED = "WEBHOOK_DELIVERY_FAILED"
    UNKNOWN = "UNKNOWN"


class ErrorResponse(BaseModel):
    """Uniform error envelope returned by API exception handlers."""

    detail: str
    code: str | None = None
