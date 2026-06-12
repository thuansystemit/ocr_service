# Sprint 1 — Foundation (Summary)

**Status:** ✅ Complete and verified in Docker (ruff + mypy + 18 tests green against Postgres 16).

Sprint 1 builds the platform skeleton that every later sprint plugs into. It does
**not** yet process documents end-to-end — see
[the scope boundary](#what-sprint-1-does-not-do-yet) below before trying to
"send a PDF in".

## What shipped

| Area | What | Where |
|------|------|-------|
| Project scaffold | pyproject, ruff, mypy, pytest config | `pyproject.toml` |
| Config | `OCR_`-prefixed settings via pydantic-settings | `app/config.py` |
| Logging | structured JSON logs + PII redaction processor | `app/observability/` |
| Metrics | Prometheus registry + `/metrics` | `app/observability/metrics.py` |
| DB layer | async SQLAlchemy engine + **tenant-scoped session (RLS)** | `app/db/session.py` |
| Worker pool | per-tenant `asyncio.Semaphore` concurrency | `app/worker/pool.py` |
| Schema | 11 tables, 24 indexes, RLS, audit triggers (migrations 001–003) | `migrations/versions/` |
| API skeleton | FastAPI app + `/health`, `/health/ready`, `/metrics`, `/docs` | `app/main.py`, `app/api/routers/health.py` |
| Deploy | Dockerfile, docker-compose (pg + qdrant + api + worker + test), K8s skeleton | `deploy/` |
| Tests | RLS adversarial suite + migration smoke + unit tests | `tests/` |

## Verification result

```
ruff check ........... All checks passed!
mypy ................. Success: no issues found in 15 source files
pytest ............... 18 passed
```

The integration tests prove, against a live Postgres, that:

- a tenant sees only its own rows;
- a tenant cannot read or forge another tenant's rows (RLS `USING` + `WITH CHECK`);
- with no tenant context set, tenant tables are inaccessible (safe-by-default);
- `audit_log` rejects `UPDATE`/`DELETE` (append-only immutability).

## What Sprint 1 does NOT do yet

There is **no document ingestion or extraction pipeline yet.** Specifically, these
do not exist until later sprints:

- `POST /api/v1/extract` (upload endpoint) — **Sprint 3**
- LlamaParse / local PDF parsing wired into the pipeline — **Sprint 3**
- LangGraph extraction workflow, guardrails, confidence, routing — **Sprints 3–5**
- Webhook delivery, human review, DLQ — **Sprints 4–5**

So you cannot yet "submit a PDF and get JSON back". What you **can** do today is
verify the foundation and run a low-level PDF *parsing* sanity check — see
[TESTING.md](./TESTING.md).
