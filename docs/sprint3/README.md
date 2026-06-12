# Sprint 3 — Ingest API + Schema Registry + Pipeline Wired (Summary)

**Status:** ✅ Complete and verified in Docker (ruff + mypy + **70 tests** green against Postgres 16, incl. an end-to-end pipeline run).
**Goal:** Ingest API · schema registry CRUD · LangGraph graph wired with Postgres checkpointing (STP happy path compilable).

## What shipped

| Task | What | Where |
|------|------|-------|
| T-022 | Pluggable `FileStorage` (local fs) + `DocumentParser` interface; `LocalParser` (pdfplumber→OCR), LlamaParse cloud stub | `app/domain/storage.py`, `app/pipeline/parsers/` |
| T-019 | Per-tenant in-flight rate limiter → `429` with `Retry-After` | `app/services/rate_limit.py` |
| T-021/023/024 | `POST /api/v1/extract` (multipart; 413/422 validation, 202+id, dry-run) + `GET /api/v1/documents/{id}` | `app/api/routers/extract.py`, `app/services/ingest.py` |
| T-026 | Schema registry CRUD (`POST/GET/PUT/GET list`), tenant-scoped | `app/api/routers/schemas.py`, `app/services/schema_registry.py` |
| T-033 | LangGraph graph builder: `parse→guardrail→extract→score→route→{deliver,review,dlq}` | `app/pipeline/graph.py`, `app/pipeline/nodes.py` |
| T-034 | `langgraph-checkpoint-postgres` wiring (`thread_id=document_id`) + worker runner + migration 005 (CREATE grant) | `app/pipeline/checkpoint.py`, `app/worker/runner.py`, `migrations/versions/005_*` |
| SP-002 | LlamaParse cloud latency/limits/fallback spike — **resolved** | `docs/sdlc/SP-002-llamaparse-spike.md` |

## Verification

```
ruff check ........... All checks passed!
mypy ................. Success: no issues found in 45 source files
pytest ............... 70 passed   (84% coverage)
```

The end-to-end test (`tests/integration/test_ingest.py`) drives a real PDF:
`POST /extract` → `documents` row → background LangGraph run **with the live
Postgres checkpointer** → terminal persistence → `GET /documents/{id}`.

## Honest status of the pipeline

The graph is **wired and runs end to end**, but two nodes are deliberately
incomplete this sprint (they are clearly marked stubs):

| Node | Sprint 3 | Becomes real in |
|------|----------|-----------------|
| parse | ✅ real (local pdfplumber + OCR) | LlamaParse cloud added Sprint 4 (T-038) |
| guardrail | minimal (pass-through) | Sprint 5 (injection/quality/length) |
| **extract** | **STUB** — returns `{}`, confidence 0 | Sprint 4 (LangChain + Qdrant RAG + Claude) |
| score | partial (stubbed confidence) | Sprint 4 (real algorithm) |
| route | ✅ real threshold routing | — |
| deliver/review/dlq | set terminal status | webhook/review fleshed out Sprints 4–5 |

**Consequence:** because `extract` is stubbed, a document's confidence is 0, so the
happy path currently routes to the **DLQ with `LOW_CONFIDENCE`**. That is expected
for Sprint 3 — it proves parse + guardrail + extract + score + route + checkpoint
all execute against real Postgres. Real field extraction (and a `completed`
outcome) arrives in Sprint 4.

## The I-003 question (LlamaParse cloud vs self-hosted)

Not a blocker: the `DocumentParser` interface means the choice is a config swap
(`OCR_PARSER_BACKEND`). Sprint 3 ships and defaults to the local backend (no cloud
dependency); Sprint 4's T-038 adds the cloud client per the SP-002 budget.

## Testing

```bash
docker compose -f deploy/docker-compose.yml --profile test run --build --rm test
```

See `docs/sprint3/TESTING.md` for driving a PDF through the live API by hand.
