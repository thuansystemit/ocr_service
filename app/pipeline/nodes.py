"""LangGraph pipeline nodes (C-10).

Each node is an async function ``(ExtractionState) -> partial update``. Nodes are
pure state transforms except ``parse_node`` (reads blob storage). Terminal DB
persistence is done by the worker runner from the final state, not inside nodes,
which keeps nodes unit-testable and side-effect-light.

Sprint status of each node:
* parse     -- real (local parser; LlamaParse cloud via parser backend, T-038)
* guardrail -- minimal (empty/quality); full guardrails in Sprint 5
* extract   -- real: Qdrant RAG few-shot + LangChain structured extraction (T-040/041)
* score     -- real: min(llm, completeness, semantic) x guardrail_mult (T-051)
* route     -- real threshold routing (HIGH/MEDIUM/LOW)
* deliver/review/dlq -- set terminal status; HMAC webhook delivery node + review
  actions are fleshed out in Sprints 5-6
"""

from __future__ import annotations

from app.observability.logging import get_logger
from app.pipeline.parsers import get_parser
from app.pipeline.parsers.base import ParserError
from app.pipeline.state import ExtractionState

log = get_logger(__name__)


def _halted(state: ExtractionState) -> bool:
    """True if the document is in a terminal pre-route state (error or cancelled);
    middle nodes no-op so the state flows untouched to the route/terminal nodes."""
    return state.get("status") in ("error", "cancelled")


async def parse_node(state: ExtractionState) -> ExtractionState:
    if state.get("is_cancelled"):
        return {"status": "cancelled", "current_step": "parse"}

    # Lazy import avoids a hard storage dependency at module import time.
    from app.domain.storage import get_storage

    content = await get_storage().load(state["file_storage_key"])
    try:
        result = await get_parser().parse(content)
    except ParserError as exc:
        log.warning("pipeline.parse.failed", document_id=state.get("document_id"), error=str(exc))
        return {"status": "error", "failure_reason": "PARSE_FAILED", "error": str(exc)}

    if result.is_empty:
        return {
            "status": "error",
            "failure_reason": "PARSE_EMPTY_OUTPUT",
            "raw_text": result.text,
            "parse_method": result.method,
            "current_step": "parse",
        }
    return {
        "raw_text": result.text,
        "parse_method": result.method,
        "current_step": "parse",
        "status": "guarding",
    }


async def guardrail_node(state: ExtractionState) -> ExtractionState:
    if _halted(state):
        return {}
    # Sprint 5 adds injection/quality/length guards. Sprint 3: pass-through.
    return {
        "guardrail_results": [],
        "guardrail_multiplier": 1.0,
        "current_step": "guardrail",
        "status": "extracting",
    }


async def extract_node(state: ExtractionState) -> ExtractionState:
    if _halted(state):
        return {}
    if state.get("extracted_json"):  # idempotent on checkpoint replay (SP-001 D-2)
        return {}

    from app.config import get_settings
    from app.pipeline.extraction import get_extraction_chain

    try:
        result = await get_extraction_chain().extract(
            tenant_id=state["tenant_id"],
            schema_id=state["schema_id"],
            schema_name=state.get("schema_name", ""),
            json_schema=state.get("json_schema", {}),
            required_fields=state.get("required_fields", []),
            text=state.get("raw_text", ""),
        )
    except Exception as exc:
        log.warning("pipeline.extract.failed", document_id=state.get("document_id"), error=str(exc))
        return {"status": "error", "failure_reason": "EXTRACTION_FAILED", "error": str(exc)}

    return {
        "extracted_json": result.fields,
        "llm_model_used": get_settings().llm_primary_model,
        "llm_token_usage": {},
        "llm_confidence": result.confidence,
        "low_confidence_fields": result.low_confidence_fields,
        "missing_fields": result.missing_fields,
        "current_step": "extract",
        "status": "scoring",
    }


async def score_node(state: ExtractionState) -> ExtractionState:
    if _halted(state):
        return {}
    from app.domain import confidence as conf_mod

    extracted = state.get("extracted_json", {})
    required = state.get("required_fields", [])
    low_conf = state.get("low_confidence_fields", [])

    completeness = conf_mod.completeness_score(extracted, required)
    llm_self = state.get("llm_confidence", 0.0)
    # Semantic proxy: penalise fields the model itself flagged as low-confidence.
    field_count = max(len(extracted), 1)
    semantic = max(0.0, 1.0 - len(low_conf) / field_count)
    mult = state.get("guardrail_multiplier", 1.0)

    breakdown = conf_mod.score(
        llm_self=llm_self, completeness=completeness, semantic=semantic, guardrail_multiplier=mult
    )
    return {
        "confidence": breakdown.guardrail_adjusted,
        "confidence_breakdown": breakdown.as_dict(),
        "missing_fields": conf_mod.missing_required(extracted, required),
        "current_step": "score",
        "status": "routing",
    }


def route_decision(state: ExtractionState) -> str:
    """Conditional edge: pick the terminal branch from confidence + thresholds."""
    if _halted(state):
        return "dlq"
    conf = state.get("confidence", 0.0)
    high = state.get("confidence_high", 0.85)
    medium = state.get("confidence_medium", 0.60)
    if conf >= high:
        return "deliver"
    if conf >= medium:
        return "review"
    return "dlq"


async def route_node(state: ExtractionState) -> ExtractionState:
    branch = route_decision(state)
    decision = {"deliver": "HIGH", "review": "MEDIUM", "dlq": "LOW"}[branch]
    return {"routing_decision": decision, "current_step": "route"}


async def deliver_node(state: ExtractionState) -> ExtractionState:
    # Sprint 5: HMAC-signed webhook with retry. Sprint 3: mark completed.
    return {"status": "completed", "current_step": "deliver"}


async def review_node(state: ExtractionState) -> ExtractionState:
    return {"status": "review", "current_step": "create_review"}


async def dlq_node(state: ExtractionState) -> ExtractionState:
    if state.get("status") == "cancelled":  # GDPR cancel: keep the cancelled state
        return {"current_step": "dlq"}
    reason = state.get("failure_reason") or "LOW_CONFIDENCE"
    return {"status": "rejected", "failure_reason": reason, "current_step": "dlq"}
