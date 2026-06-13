# OCR Platform — MVP Status

**As of end of Sprint 6 — pilot-ready MVP (milestone M-4).**
Verified in Docker: ruff + mypy clean, **126 tests passing** against Postgres 16.

## The capability, end to end

A client authenticates (API key or JWT), the platform parses an uploaded document
(LlamaParse cloud or local OCR fallback), runs guardrails, extracts structured
fields with an LLM grounded by tenant-scoped few-shot RAG, scores confidence, and
routes the result: **HIGH → webhook (straight-through), MEDIUM → human review,
LOW/blocked → dead-letter.** Everything is multi-tenant-isolated, audited, and
GDPR-erasable.

## What's built, by sprint

| Sprint | Theme | Verified |
|--------|-------|----------|
| 1 | Foundation: config, structured logging, async DB + **RLS**, worker pool, 11-table schema, Docker/K8s | ✅ |
| 2 | ORM + Pydantic, **AES-256-GCM PII encryption**, JWT + API-key auth, tenant-context middleware, checkpoint spike | ✅ |
| 3 | Ingest API, file storage, parser interface, **LangGraph pipeline + Postgres checkpointing**, schema CRUD | ✅ |
| 4 | **Qdrant RAG (tenant-guarded)**, LangChain extraction, confidence scoring, webhook signing, review queue, LlamaParse client | ✅ |
| 5 | **Guardrails**, webhook delivery + retry, **DLQ API**, **circuit breaker + GPT-4o fallback**, audit service | ✅ |
| 6 | Schema lifecycle/activation, **review actions** + active learning, **GDPR in-flight erasure**, audit export | ✅ |

## API surface

```
POST   /api/v1/extract                 upload a document for extraction (202)
GET    /api/v1/documents/{id}          status + extracted result
DELETE /api/v1/documents/{id}          GDPR erasure
POST   /api/v1/schemas                 create draft schema
POST   /api/v1/schemas/{id}/seeds      add a labelled few-shot example
POST   /api/v1/schemas/{id}/activate   activate (>=3 seeds)
GET    /api/v1/schemas[/{id}]          list / get
GET    /api/v1/review[/{id}]           human review queue
POST   /api/v1/review/{id}             accept / correct / reject
GET    /api/v1/dlq[/{id}]              dead-letter queue
POST   /api/v1/dlq/{id}/retry          re-enter the pipeline
GET    /api/v1/audit/export            NDJSON/CSV audit trail
GET    /api/v1/me, /me/schemas/count   identity / RLS check
GET    /health, /health/ready, /metrics
```

## Enterprise properties (and where they're proven)

| Property | Mechanism | Test |
|----------|-----------|------|
| Tenant isolation | PostgreSQL RLS on 10 tables + `SET LOCAL` | `test_rls.py` |
| No cross-tenant RAG leakage | Qdrant mandatory filter + post-query assertion | `test_qdrant_service.py` |
| PII at rest | AES-256-GCM, per-tenant HKDF key, tenant-bound AAD | `test_encryption.py` |
| Auditability | append-only `audit_log` (SHA-256 hash, PG trigger) | `test_audit.py`, `test_migrations.py` |
| Crash recovery | LangGraph Postgres checkpoints, idempotent nodes | `test_checkpoint_recovery.py` |
| Resilience | circuit breaker → GPT-4o fallback; webhook retry → DLQ | `test_circuit_breaker.py`, `test_webhook_delivery.py` |
| GDPR erasure | cancel → externals → rows → tombstone (crash-safe) | `test_erasure.py` |
| Concurrency safety | optimistic locking on review/document `version` | `test_review_actions.py` |

## Run it

```bash
# dev stack (apply code changes by re-running):
docker compose -f deploy/docker-compose.yml up -d --build

# full verification (lint + types + 126 tests):
docker compose -f deploy/docker-compose.yml --profile test run --build --rm test
```

Set `ANTHROPIC_API_KEY` (+ `OPENAI_API_KEY` for RAG embeddings) to run real
extractions; without them the pipeline parses locally and routes to the DLQ.

## Open items before a real pilot launch

- **I-001** LLM/parse provider **DPAs** signed before processing real PII.
- **I-002** confirm the invoice **required-field set** with the pilot tenant.
- **I-003** finalize **LlamaParse cloud vs self-hosted** (interface already abstracts it).
- Pre-launch hardening: full 51-Gherkin sweep, Grafana dashboards, OpenTelemetry
  tracing, retention-purge cron, SSO — none are new features, all are operational.
- Not yet committed to git.
