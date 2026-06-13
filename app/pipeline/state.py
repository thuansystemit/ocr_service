"""ExtractionState -- the LangGraph pipeline state object (T-032, REQ-052).

This dict is the single value threaded through every pipeline node and persisted
by the Postgres checkpointer after each node (``thread_id = document_id``). Keep
it JSON-serialisable: only str/int/float/bool/list/dict/None, no ORM objects or
datetimes-as-objects (use ISO strings). See
``docs/sdlc/SP-001-langgraph-checkpoint-recovery.md`` for why each node must read
its inputs from, and write its outputs back to, this state rather than relying on
in-memory locals.

``is_cancelled`` is checked between nodes to support GDPR in-flight erasure
(EC-005); ``current_step`` records the last completed node for crash recovery
(EC-012).
"""

from __future__ import annotations

from typing import Any, TypedDict


class ExtractionState(TypedDict, total=False):
    # --- Identity (immutable after START) ---
    document_id: str
    tenant_id: str
    schema_id: str
    schema_version: int
    schema_name: str
    file_storage_key: str
    mime_type: str

    # --- Schema-derived inputs (seeded at START) ---
    confidence_high: float
    confidence_medium: float
    json_schema: dict[str, Any]
    required_fields: list[str]
    pii_fields: list[str]

    # --- Pipeline progress / control ---
    status: str  # DocumentStatus value
    current_step: str  # last completed node, for checkpoint recovery
    is_cancelled: bool  # set by GDPR erasure; checked between nodes
    started_at: str  # ISO 8601
    updated_at: str  # ISO 8601

    # --- Parse output ---
    raw_text: str
    parse_method: str  # "llamaparse" | "fallback"

    # --- Guardrails (each entry is GuardrailOutcome.as_state(): name/result/detail/multiplier) ---
    guardrail_results: list[dict[str, Any]]
    guardrail_multiplier: float

    # --- Extraction ---
    extracted_json: dict[str, Any]
    llm_model_used: str
    llm_token_usage: dict[str, int]
    llm_confidence: float

    # --- Scoring / routing ---
    confidence: float
    confidence_breakdown: dict[str, float]
    low_confidence_fields: list[str]
    missing_fields: list[str]
    routing_decision: str  # "HIGH" | "MEDIUM" | "LOW"

    # --- Terminal ---
    failure_reason: str  # FailureReason value when routed to DLQ
    error: str  # human-readable error detail
