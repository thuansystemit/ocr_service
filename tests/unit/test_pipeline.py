"""Pipeline graph + node unit tests (T-033)."""

from __future__ import annotations

import uuid

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.pipeline import nodes
from app.pipeline.extraction import LLMExtraction, set_extraction_chain
from app.pipeline.graph import compile_graph
from app.pipeline.state import ExtractionState
from tests.conftest import make_text_pdf


# --- route_decision ------------------------------------------------------- #
@pytest.mark.parametrize(
    ("conf", "expected"),
    [
        (0.95, "deliver"),
        (0.85, "deliver"),
        (0.7, "review"),
        (0.60, "review"),
        (0.59, "dlq"),
        (0.0, "dlq"),
    ],
)
def test_route_decision_thresholds(conf: float, expected: str) -> None:
    state: ExtractionState = {
        "confidence": conf,
        "confidence_high": 0.85,
        "confidence_medium": 0.60,
    }
    assert nodes.route_decision(state) == expected


def test_route_decision_error_goes_to_dlq() -> None:
    assert nodes.route_decision({"status": "error", "confidence": 0.99}) == "dlq"


# --- individual nodes ----------------------------------------------------- #
async def test_extract_node_is_idempotent() -> None:
    out = await nodes.extract_node({"extracted_json": {"x": 1}})
    assert out == {}  # already extracted -> no-op (SP-001 D-2)


async def test_guardrail_passes_through() -> None:
    out = await nodes.guardrail_node({"raw_text": "hello"})
    assert out["status"] == "extracting"
    assert out["guardrail_multiplier"] == 1.0


# --- full graph run ------------------------------------------------------- #
class _FakeStorage:
    async def save(self, tenant_id: object, document_id: object, content: bytes) -> str:
        return "k"

    async def load(self, storage_key: str) -> bytes:
        return make_text_pdf("Invoice 1 Total 9.00")

    async def delete(self, storage_key: str) -> None:
        return None


class _FakeChain:
    async def extract(self, **_: object) -> LLMExtraction:
        return LLMExtraction(fields={"total": "9.00"}, confidence=0.95)


async def test_graph_runs_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.domain.storage.get_storage", lambda: _FakeStorage())
    set_extraction_chain(_FakeChain())  # type: ignore[arg-type]
    try:
        graph = compile_graph(MemorySaver())
        initial: ExtractionState = {
            "document_id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "schema_id": str(uuid.uuid4()),
            "file_storage_key": "k",
            "confidence_high": 0.85,
            "confidence_medium": 0.60,
            "required_fields": [],
            "json_schema": {},
            "status": "pending",
            "is_cancelled": False,
        }
        final = await graph.ainvoke(initial, {"configurable": {"thread_id": "t1"}})

        # Parse ran, fake extraction is high-confidence -> straight-through to completed.
        assert "Invoice 1" in final["raw_text"]
        assert final["parse_method"] == "local"
        assert final["extracted_json"] == {"total": "9.00"}
        assert final["routing_decision"] == "HIGH"
        assert final["status"] == "completed"
    finally:
        set_extraction_chain(None)


async def test_graph_cancelled_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.domain.storage.get_storage", lambda: _FakeStorage())
    graph = compile_graph(MemorySaver())
    initial: ExtractionState = {
        "document_id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "file_storage_key": "k",
        "status": "pending",
        "is_cancelled": True,
    }
    final = await graph.ainvoke(initial, {"configurable": {"thread_id": "t2"}})
    assert final["status"] in ("cancelled", "rejected")  # cancelled at parse
