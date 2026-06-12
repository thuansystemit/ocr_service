# SP-001 — LangGraph checkpoint-postgres recovery semantics (Spike)

**Date:** 2026-06-12 · **Sprint:** 2 · **Gates:** T-033/T-034 (Sprint 3 pipeline build)
**Risk addressed:** EC-012 (mid-pipeline crash → resume without duplicate LLM calls)

## Question

When a LangGraph run is interrupted (worker crash, pod eviction, timeout) and the
graph is later invoked again with the **same `thread_id`**, does it:

1. resume from the last completed node, or re-execute the whole graph?
2. re-run nodes whose work (and side effects — LLM calls, DB writes) already
   completed?

## Findings

**1. Resume is checkpoint-driven and automatic.** The checkpointer persists a
snapshot of the channel/state values after **each node** completes, keyed by
`thread_id`. Re-invoking the graph with the same `thread_id` and `input=None`
resumes from the saved snapshot: **already-completed nodes are not re-executed.**
Execution continues from the next pending node. This is verified by
`tests/unit/test_checkpoint_recovery.py`, which interrupts a 2-node graph after
node A and asserts node A's side-effect counter stays at 1 after resume.

**2. Node *replay* can happen for the node that was mid-flight at crash time.**
The checkpoint is written *after* a node returns. If a worker dies **while a node
is executing** (before it returned), there is no checkpoint for that node, so on
resume that node runs again from the start. Therefore: **a node that performs an
external side effect (LLM call, webhook POST, DB insert) can be entered more than
once across a crash.** LangGraph guarantees "completed nodes don't re-run"; it
does **not** make a half-finished node's side effects idempotent for you.

**3. Consequence for the EXTRACT node (the expensive one).** To honour
"no duplicate LLM calls" we cannot rely on the checkpointer alone. The node must
be **idempotent at its own boundary**: check whether its output already exists
before performing the side effect.

## Decisions (feed into T-033 / T-034)

- **D-SP001-1 — `thread_id = document_id`.** One graph thread per document gives a
  1:1 mapping between a document and its checkpoint history; recovery is "re-invoke
  the graph for every document still in a non-terminal status" on worker startup
  (uses `idx_documents_pending_recovery`).
- **D-SP001-2 — Idempotent EXTRACT node.** The node first checks
  `state.get("extracted_json")`; if already populated (restored from checkpoint),
  it skips the LLM call. As a second guard, the extraction-result DB row is keyed
  `UNIQUE(document_id)`, so a duplicate insert fails fast rather than double-billing
  downstream.
- **D-SP001-3 — Use the async saver.** Production uses
  `langgraph.checkpoint.postgres.aio.AsyncPostgresSaver` (the app is fully async).
  Call `await saver.setup()` once at worker startup to create the checkpoint
  tables. Reuse one saver per process.
- **D-SP001-4 — Checkpoint lifecycle = document lifecycle.** Checkpoints for a
  `thread_id` are deleted when the document is hard-deleted (GDPR erasure / retention
  purge), via `DELETE FROM checkpoints WHERE thread_id = :document_id` in the same
  transaction as the document delete. (Covered in Sprint 6, T-075/T-076.)
- **D-SP001-5 — Recovery scan on startup.** The worker, on boot, selects documents
  in in-flight statuses and re-invokes their threads with `input=None` to resume.

## Production saver wiring (reference for T-033)

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# once per process, at worker/app startup:
saver = AsyncPostgresSaver.from_conn_string(settings.checkpoint_dsn)
await saver.setup()                      # creates checkpoint tables if absent
graph = build_graph().compile(checkpointer=saver)

# per document:
config = {"configurable": {"thread_id": document_id}}
await graph.ainvoke(initial_state, config)        # first run
await graph.ainvoke(None, config)                 # resume after a crash
```

> Note: the checkpointer needs a libpq/psycopg connection string (`postgresql://…`),
> not the SQLAlchemy/asyncpg URL form. Sprint 3 adds a derived `checkpoint_dsn`
> setting.

## Residual risks / follow-ups

- **R-1:** A node that crashes repeatedly mid-execution will retry indefinitely on
  each recovery scan. Mitigate with the existing retry/circuit-breaker budget
  (T-040/T-057) and route to DLQ after N attempts.
- **R-2:** Idempotency for the WEBHOOK node is handled separately by the
  `webhook_deliveries` attempt log + dedup, not by the checkpointer (Sprint 5).

**Spike outcome:** resolved. The "resume vs re-execute" semantics are understood
and the one gap (mid-flight node replay) has a concrete mitigation (idempotent
nodes + unique constraints). T-033/T-034 are unblocked.
