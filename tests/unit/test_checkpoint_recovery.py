"""SP-001 validation: LangGraph checkpoint resume semantics.

Proves the core finding behind EC-012: when a graph is interrupted after a node
completes and then resumed with the same ``thread_id``, the completed node is
**not** re-executed (its side effect runs exactly once). This is the property the
pipeline relies on to avoid duplicate LLM calls after a crash.

Uses MemorySaver -- the saver only changes *where* checkpoints are stored, not the
execution semantics, so the assertion holds identically for the Postgres saver
used in production (thread_id = document_id).

Note: the State TypedDicts are module-level on purpose -- LangGraph resolves node
type hints via ``get_type_hints``, which cannot see a class defined inside a test
function. Graph inputs are also non-empty: a superstep that writes to no channel
raises ``InvalidUpdateError``.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph


class _ResumeState(TypedDict, total=False):
    a_done: bool
    b_done: bool


async def test_completed_node_not_reexecuted_on_resume() -> None:
    side_effects = {"a": 0, "b": 0}

    async def node_a(state: _ResumeState) -> _ResumeState:
        side_effects["a"] += 1  # stand-in for an expensive LLM call
        return {"a_done": True}

    async def node_b(state: _ResumeState) -> _ResumeState:
        side_effects["b"] += 1
        return {"b_done": True}

    builder = StateGraph(_ResumeState)
    builder.add_node("node_a", node_a)
    builder.add_node("node_b", node_b)
    builder.add_edge(START, "node_a")
    builder.add_edge("node_a", "node_b")
    builder.add_edge("node_b", END)

    # interrupt_before simulates a crash after node_a's checkpoint, before node_b.
    graph = builder.compile(checkpointer=MemorySaver(), interrupt_before=["node_b"])
    config = {"configurable": {"thread_id": "doc-123"}}

    # First run: executes node_a, then halts before node_b.
    state1 = await graph.ainvoke({"a_done": False, "b_done": False}, config)
    assert state1["a_done"] is True
    assert state1["b_done"] is False
    assert side_effects == {"a": 1, "b": 0}

    # Resume (input=None) with the same thread_id: only node_b runs.
    state2 = await graph.ainvoke(None, config)
    assert state2["a_done"] is True
    assert state2["b_done"] is True

    # node_a's side effect ran exactly once across the crash + resume.
    assert side_effects == {"a": 1, "b": 1}


class _ExtractState(TypedDict, total=False):
    extracted_json: dict


async def test_idempotent_node_skips_side_effect_when_output_present() -> None:
    """D-SP001-2: a node that finds its output already in state skips the side effect.

    Belt-and-suspenders for the one gap (a node that crashed *mid-flight* re-runs
    on resume). The skip branch re-writes the existing value -- a valid no-op
    channel write -- rather than returning ``{}`` (which LangGraph rejects)."""
    calls = {"extract": 0}

    async def extract(state: _ExtractState) -> _ExtractState:
        if state.get("extracted_json"):
            return {"extracted_json": state["extracted_json"]}  # restored -> no LLM call
        calls["extract"] += 1
        return {"extracted_json": {"total": "1.00"}}

    builder = StateGraph(_ExtractState)
    builder.add_node("extract", extract)
    builder.add_edge(START, "extract")
    builder.add_edge("extract", END)
    graph = builder.compile()

    # Cold run -> performs the side effect.
    out1 = await graph.ainvoke({"extracted_json": {}})
    assert out1["extracted_json"] == {"total": "1.00"}
    assert calls["extract"] == 1

    # Simulated replay with output already present -> side effect skipped.
    out2 = await graph.ainvoke({"extracted_json": {"total": "1.00"}})
    assert out2["extracted_json"] == {"total": "1.00"}
    assert calls["extract"] == 1
