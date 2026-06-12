"""LangGraph extraction graph builder (T-033).

    START -> parse -> guardrail -> extract -> score -> route
                                                          |
                              route_decision (conditional)
                              /            |             \\
                        deliver         review           dlq
                              \\            |             /
                                         END

The compiled graph is checkpointed (``thread_id = document_id``) so a crashed run
resumes from its last completed node (SP-001). The terminal nodes set the final
document status in state; the worker runner persists it.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.pipeline import nodes
from app.pipeline.state import ExtractionState


def build_graph() -> StateGraph:
    g = StateGraph(ExtractionState)

    g.add_node("parse", nodes.parse_node)
    g.add_node("guardrail", nodes.guardrail_node)
    g.add_node("extract", nodes.extract_node)
    g.add_node("score", nodes.score_node)
    g.add_node("route", nodes.route_node)
    g.add_node("deliver", nodes.deliver_node)
    g.add_node("review", nodes.review_node)
    g.add_node("dlq", nodes.dlq_node)

    g.add_edge(START, "parse")
    g.add_edge("parse", "guardrail")
    g.add_edge("guardrail", "extract")
    g.add_edge("extract", "score")
    g.add_edge("score", "route")
    g.add_conditional_edges(
        "route",
        nodes.route_decision,
        {"deliver": "deliver", "review": "review", "dlq": "dlq"},
    )
    g.add_edge("deliver", END)
    g.add_edge("review", END)
    g.add_edge("dlq", END)
    return g


def compile_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    """Compile the graph. Pass a checkpointer (Postgres in prod, Memory in tests);
    ``None`` compiles a checkpoint-less graph for pure structural tests."""
    return build_graph().compile(checkpointer=checkpointer)
