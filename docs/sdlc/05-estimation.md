# Estimates — Enterprise OCR / Document-Extraction Platform (MVP)
**Date:** 2026-06-09
**Author:** @estimator
**Status:** REVIEWED
**Sources:** `01-product-spec.md`, `02-requirements.md`, `03-architecture.md`, `04-data-model.md`

---

## Assumptions

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Team size | 2 senior engineers | Startup/pilot team; can be parallelized on independent epics |
| Velocity | 20 story points / sprint | Conservative: 2 engineers × 10 pts each; accounts for ceremonies, review, ramp |
| Sprint length | 2 weeks | Standard Agile cadence |
| Total sprints | 4 (MVP Phase 1) | Per product spec constraint |
| Working days/sprint | 10 days/engineer | No significant holidays assumed |
| Inflation applied | See per-task risk flags | LlamaParse, RLS correctness, LangGraph checkpoint, GDPR in-flight |
| File storage | Local filesystem (dev) | DM-002 unresolved; S3 path deferred to Phase 2 |
| LlamaParse | Cloud API | I-003 resolved as cloud for MVP; self-hosted evaluation Phase 2 |
| Qdrant vector dim | 1536 | DM-004 defaulting to 1536 (OpenAI-compatible embedding dimension) |

---

## Epic Overview

| Epic | Components | User Stories | Total Points |
|------|------------|--------------|-------------|
| E-01 Foundation & Infrastructure | C-06, C-17, deployment | US-004, NFR | 23 |
| E-02 Data Layer & Migrations | All 11 tables, RLS, audit triggers | US-004, US-005, NFR | 21 |
| E-03 Auth & Multi-Tenancy | C-01, C-06, C-08 | US-004 | 18 |
| E-04 Ingest API | C-01, C-02 | US-001 | 13 |
| E-05 Schema Registry | C-03 | US-003 | 16 |
| E-06 LangGraph Pipeline Core | C-10, C-11, C-17 | US-001, NFR | 21 |
| E-07 Extraction + RAG | C-13, C-18 | US-001 | 18 |
| E-08 Guardrails | C-12 | US-001, US-004 | 13 |
| E-09 Confidence Scoring & Routing | C-09, C-14 | US-001, US-002, US-006 | 10 |
| E-10 Webhook Delivery | C-15 | US-001, US-006 | 11 |
| E-11 DLQ & Circuit Breaker | C-16, C-19 | US-006 | 13 |
| E-12 Human Review Module | C-04 | US-002 | 21 |
| E-13 Audit Service | C-07 | US-005 | 10 |
| E-14 GDPR & Retention | C-05, C-22 | US-005 | 16 |
| E-15 Observability & Alerts | C-20, C-21 | US-006, NFR | 13 |
| **TOTAL** | | | **237** |

---

## Task Breakdown

### E-01 — Foundation & Infrastructure

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-001 | Project scaffold: FastAPI app factory, config management (pydantic-settings), environment hierarchy (dev/test/prod), logging setup with structlog | infra | NFR | 3 | ~2 | — | low |
| T-002 | Docker Compose: postgres 16 + qdrant + app + worker services; volume mounts; health checks | infra | NFR | 2 | ~1 | T-001 | low |
| T-003 | Async SQLAlchemy 2.0 engine + session factory; connection pool config; per-request session dependency | backend | NFR | 2 | ~1 | T-001 | low |
| T-004 | asyncio.Semaphore worker pool (C-17): per-tenant semaphore map, submit/release, configurable concurrency; HPA readiness | backend | REQ-052, NFR | 3 | ~2 | T-001 | low |
| T-005 | Structured JSON log formatter: tenant_id, document_id, redaction filter for PII fields ([REDACTED] mask) | infra | REQ-053, REQ-031 | 3 | ~2 | T-001 | low |
| T-006 | Alembic init: env.py for async engine, revision template, makefile targets (upgrade/downgrade/autogenerate) | infra | NFR | 2 | ~1 | T-003 | low |
| T-007 | Kubernetes manifests: Deployment + HPA for app/worker, ConfigMap, Secrets template, Service, Ingress skeleton | infra | NFR | 3 | ~2 | T-002 | low |
| T-008 | CI pipeline: lint (ruff), type-check (mypy), unit tests (pytest-asyncio), Docker build | infra | NFR | 3 | ~2 | T-001 | low |
| **E-01 subtotal** | | | | **21** | | | |

> Note: T-007 (k8s manifests) is skeleton only — prod hardening is Phase 2. Estimated 3 pts because env-specific tuning of HPA thresholds requires load test data.

---

### E-02 — Data Layer & Migrations

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-009 | Alembic migration 001_initial_schema: all 11 tables (tenants, api_keys, schemas, schema_versions, documents, extraction_results, guardrail_reports, review_tasks, audit_log, dlq, webhook_deliveries) | database | REQ-029, all | 5 | ~3–4 | T-006 | medium |
| T-010 | Alembic migration 002_rls_policies: RLS ENABLE + CREATE POLICY for all 10 tenant-scoped tables; ocr_admin bypass role | database | REQ-029, US-004 | 3 | ~2 | T-009 | medium |
| T-011 | Alembic migration 003_audit_triggers: trg_audit_no_update + trg_audit_no_delete on audit_log; schema activation gate trigger (seed_count >= 3) | database | REQ-037, REQ-026 | 3 | ~2 | T-009 | medium |
| T-012 | SQLAlchemy ORM models: all 11 tables as mapped dataclasses; relationship declarations; optimistic lock event listener (StaleDataError -> 409) | backend | all | 5 | ~3–4 | T-009 | low |
| T-013 | Pydantic v2 schemas: all 16 models (TenantBase, CreateSchemaRequest, ExtractRequest, DocumentResponse, etc.); model_validator for confidence thresholds | backend | all | 3 | ~2 | T-012 | low |
| T-014 | RLS middleware integration test: verify SET LOCAL + policy enforcement; cross-tenant leak assertion; ocr_admin bypass | test | REQ-029 | 2 | ~1 | T-010, T-012 | medium |
| **E-02 subtotal** | | | | **21** | | | |

> T-009 at 5 pts: 11 tables, 24 indexes, multiple FK constraints, UUID PKs, JSONB columns, BIGINT, TEXT[] arrays — non-trivial to get right first pass. T-010 at 3 pts: RLS policy DDL is straightforward but incorrect policies are a silent security failure — inflation applied (×1.3 correctness risk).

---

### E-03 — Auth & Multi-Tenancy

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-015 | JWT RS256 middleware: extract tenant_id from claim, populate contextvars + SET LOCAL app.current_tenant_id; 401 on missing/invalid | backend | REQ-028, REQ-034 | 3 | ~2 | T-012 | low |
| T-016 | API key auth: SHA-256 hash lookup, revocation check (revoked_at IS NOT NULL), <100ms p95; cache hot keys (TTL 60s in-process LRU) | backend | REQ-032, REQ-034 | 3 | ~2 | T-012 | low |
| T-017 | Tenant context propagation (C-06): contextvars.ContextVar for tenant_id; FastAPI dependency; SQLAlchemy event hook for SET LOCAL; scope test | backend | REQ-029, US-004 | 3 | ~2 | T-015, T-016 | medium |
| T-018 | PII encryption service (C-08): AES-256-GCM field-level encrypt/decrypt for pii_fields[] in extracted_json; key derivation (tenant-specific nonce); log masking decorator | backend | REQ-031, US-004 | 5 | ~3–4 | T-015 | medium |
| T-019 | Rate limiting middleware: per-tenant queue size check (max_queue_size), 429 response; asyncio counter per tenant | backend | REQ-035 | 2 | ~1 | T-017 | low |
| T-020 | Auth + RLS integration tests: JWT valid/invalid/expired, API key create/revoke round-trip, cross-tenant isolation test (select from another tenant's documents) | test | REQ-028–034 | 2 | ~1 | T-015–T-019 | low |
| **E-03 subtotal** | | | | **18** | | | |

> T-018 at 5 pts: AES-256-GCM implementation with per-tenant key derivation and nonce management is security-critical; correctness matters more than speed. Needs separate security review.

---

### E-04 — Ingest API

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-021 | POST /api/v1/extract endpoint: multipart file upload, file size check (413 >50MB), MIME validation (422), document_type validation (422), return 202+document_id within 500ms | backend | REQ-001, REQ-006–REQ-008 | 3 | ~2 | T-017 | low |
| T-022 | File storage adapter: local filesystem (dev) / pluggable interface; store to file_storage_key, async write; content-type recorded | backend | DM-002, US-001 | 2 | ~1 | T-021 | low |
| T-023 | Document record creation + enqueue: insert documents row (status=PENDING), enqueue document_id to worker pool, return 202; idempotency check on re-submit | backend | REQ-001, REQ-052 | 2 | ~1 | T-021, T-004 | low |
| T-024 | Dry-run flag handling: is_dry_run=true skips persist + webhook; returns extraction preview response | backend | REQ-023, US-003 | 2 | ~1 | T-023 | low |
| T-025 | Ingest API integration tests: happy-path 202, 413 oversized, 422 bad MIME, 422 unknown doc_type, 500ms SLA assertion, dry-run mode | test | REQ-001–REQ-008 | 2 | ~1 | T-021–T-024 | low |
| **E-04 subtotal** | | | | **11** | | | |

---

### E-05 — Schema Registry

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-026 | Schema CRUD API: POST /schemas (draft), GET /schemas/{id}, PUT /schemas/{id}, GET /schemas (list, tenant-scoped) | backend | REQ-021, US-003 | 3 | ~2 | T-017 | low |
| T-027 | Schema versioning: version increment on activate; schema_versions row created on each activation; in-flight docs pin schema_version | backend | REQ-025, US-003 | 3 | ~2 | T-026 | medium |
| T-028 | Seed example management: POST /schemas/{id}/seeds (upload example doc + expected JSON), validate, store to Qdrant (tenant-scoped), increment seed_count | backend | REQ-022, REQ-027, US-003 | 3 | ~2 | T-026, T-048 | medium |
| T-029 | Activation gate: block activation if seed_count < 3 (REQ-026); transition DRAFT->ACTIVE->DEPRECATED; PG trigger enforcement + API-layer check | backend | REQ-024, REQ-026, US-003 | 2 | ~1 | T-028 | low |
| T-030 | Schema activation no-redeployment test: activate schema, immediately submit document, assert pipeline uses new version | test | REQ-024, US-003 | 2 | ~1 | T-029, T-023 | low |
| T-031 | Schema Registry integration tests: CRUD, seed upload, activation gate (< 3 seeds blocked), versioning, tenant isolation | test | REQ-021–REQ-027 | 3 | ~2 | T-026–T-030 | low |
| **E-05 subtotal** | | | | **16** | | | |

---

### E-06 — LangGraph Pipeline Core

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-032 | ExtractionState TypedDict: all fields (document_id, tenant_id, schema_id, schema_version, status, raw_text, guardrail_results, extracted_json, confidence, routing_decision, error, is_cancelled) | backend | REQ-052, US-001 | 2 | ~1 | T-001 | low |
| T-033 | LangGraph graph builder: define nodes (PARSE, GUARDRAIL, EXTRACT, SCORE, ROUTE, WEBHOOK, CREATE_REVIEW, DLQ_WRITE, COMPLETE), conditional edges, entry point | backend | REQ-052, US-001 | 5 | ~3–4 | T-032 | high |
| T-034 | langgraph-checkpoint-postgres setup: CheckpointSaver wired to async PG pool; thread_id = document_id; resume-from-checkpoint on worker restart | backend | REQ-052, EC-012 | 5 | ~3–4 | T-033, T-003 | high |
| T-035 | Pipeline worker: async task runner picks document_id from queue, loads LangGraph graph, invokes with initial state, handles exceptions, updates document.status on completion | backend | REQ-052, US-001 | 3 | ~2 | T-033, T-004 | medium |
| T-036 | GDPR cancellation flag: is_cancelled check between every node transition; if set, skip remaining nodes, purge checkpoint, tombstone audit | backend | REQ-041, US-005 | 5 | ~3–4 | T-033 | high |
| T-037 | Pipeline crash recovery test: kill worker mid-pipeline, restart, assert resume from last checkpoint; cross-tenant state leakage test | test | REQ-052, EC-012 | 3 | ~2 | T-034, T-035 | high |
| **E-06 subtotal** | | | | **23** | | | |

> T-033 at 5 pts: LangGraph API surface is well-documented but conditional edge logic for 9 nodes, error state transitions, and GDPR cancellation path is non-trivial. First integration with the full graph warrants a spike.
> T-034 at 5 pts: langgraph-checkpoint-postgres is a third-party integration with limited production track record. Recovery semantics (partial node re-execution) need to be validated.
> T-036 at 5 pts: GDPR in-flight cancellation requires atomic: set flag, interrupt async task, purge PG checkpoint rows, delete Qdrant vectors, write tombstone. Complex cross-system transaction.

---

### E-07 — Extraction + RAG

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-038 | LlamaParse cloud client (C-11): async HTTP client, API key from config, retry 3×, pdfplumber fallback on 5xx/timeout, pytesseract fallback on pdfplumber failure | backend | REQ-002, US-001 | 5 | ~3–4 | T-033 | high |
| T-039 | Qdrant service wrapper (C-18): async client, mandatory tenant_id filter injection, post-query assertion (raise CRITICAL if tenant_id absent), vector upsert for seed/correction | backend | REQ-030, REQ-033, US-001 | 3 | ~2 | T-001 | medium |
| T-040 | RAG few-shot retrieval: embed input text (OpenAI-compatible embedding), query Qdrant with tenant_id + schema_id filters, top-K examples, prompt builder | backend | REQ-033, US-001 | 3 | ~2 | T-039 | medium |
| T-041 | LangChain LCEL extraction chain (C-13): BaseChatModel abstraction, primary Claude claude-sonnet-4-6, fallback GPT-4o via C-19, structured output (Pydantic), prompt template with few-shot injection | backend | REQ-002, REQ-003, US-001 | 5 | ~3–4 | T-040 | medium |
| T-042 | Extraction result persistence: insert extraction_results row, encrypt pii_fields[] via C-08, compute extracted_json_hash, record llm_model_used + token_usage | backend | REQ-036, US-001 | 2 | ~1 | T-041, T-018 | low |
| T-043 | LlamaParse integration test: mock LlamaParse cloud, assert retry on 5xx, assert pdfplumber fallback, assert pytesseract fallback | test | REQ-002 | 2 | ~1 | T-038 | medium |
| T-044 | Cross-tenant RAG isolation test: seed examples for tenant A, query as tenant B, assert zero results; assertion fires on filter omission | test | REQ-030, REQ-033 | 2 | ~1 | T-039, T-040 | high |
| **E-07 subtotal** | | | | **22** | | | |

> T-038 at 5 pts: LlamaParse cloud API is an external dependency with no SLA guarantee at MVP; retry logic, fallback chain, and timeout handling add significant complexity (I-003). Marked external dep ×1.5.
> T-041 at 5 pts: LangChain LCEL with structured output + BaseChatModel abstraction is well-trodden but prompt engineering for structured invoice extraction requires iteration.

---

### E-08 — Guardrails

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-045 | Guardrail base interface: abstract GuardrailBase with run() -> GuardrailResult; result enum (PASS/WARN/BLOCK); pipeline multiplier aggregation | backend | US-001 | 2 | ~1 | T-032 | low |
| T-046 | Injection detection guardrail: regex + heuristic scan of raw_text for prompt injection patterns; BLOCK on detection | backend | REQ-013, US-001 | 3 | ~2 | T-045 | medium |
| T-047 | Text quality guardrail: empty text check, min length threshold, character entropy check; WARN on low quality | backend | US-001 | 2 | ~1 | T-045 | low |
| T-048 | Guardrail pipeline node: run all guardrails in sequence, collect guardrail_reports, compute aggregate confidence_multiplier (product of WARN multipliers), BLOCK -> DLQ, WARN -> multiply confidence | backend | REQ-013, US-001 | 3 | ~2 | T-046, T-047 | medium |
| T-049 | Guardrail reports persistence: insert guardrail_reports rows for each check result; link to document_id | backend | US-001 | 1 | ~0.5 | T-048, T-042 | low |
| T-050 | Guardrail unit + integration tests: injection pattern blocked, quality warn produces multiplier, BLOCK routes to DLQ, PASS proceeds | test | REQ-013 | 3 | ~2 | T-045–T-049 | low |
| **E-08 subtotal** | | | | **14** | | | |

---

### E-09 — Confidence Scoring & Routing

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-051 | Confidence scorer (C-09): compute min(llm_self, completeness_score, semantic_score) × guardrail_multiplier; completeness = required fields present/total; semantic = cosine similarity against seed examples | backend | REQ-003, REQ-004, REQ-009, REQ-010 | 5 | ~3–4 | T-041, T-048 | medium |
| T-052 | Route node (C-14): HIGH(>=0.85) -> WEBHOOK, MEDIUM(>=0.60) -> CREATE_REVIEW, LOW(<0.60) -> DLQ_WRITE; update documents.routing_decision | backend | REQ-003, REQ-009, REQ-010 | 2 | ~1 | T-051 | low |
| T-053 | Configurable thresholds: read confidence_high / confidence_medium from schema row; per-schema override takes priority | backend | REQ-055, US-003 | 1 | ~0.5 | T-052 | low |
| T-054 | Confidence + routing tests: assert boundary conditions (0.85/0.84, 0.60/0.59), missing required field forces LOW, guardrail WARN lowers score | test | REQ-003–REQ-010 | 2 | ~1 | T-051–T-053 | low |
| **E-09 subtotal** | | | | **10** | | | |

> T-051 at 5 pts: semantic scoring requires embedding lookup against seed examples and cosine similarity computation — adds latency budget pressure within the 15s p95 SLA. Needs benchmarking.

---

### E-10 — Webhook Delivery

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-055 | Webhook payload builder: sign with HMAC-SHA256 using tenant.webhook_secret, add X-OCR-Signature header, serialize extraction result | backend | REQ-011, US-001 | 2 | ~1 | T-041 | low |
| T-056 | Webhook delivery node: async HTTP POST with timeout; record to webhook_deliveries; retry schedule [1,5,30,120,600]s exponential backoff | backend | REQ-005, REQ-012, US-001 | 3 | ~2 | T-055 | low |
| T-057 | Webhook exhaustion -> DLQ: after 5 failed attempts, write to dlq with last_http_status; write webhook EXHAUSTED audit event | backend | REQ-012, REQ-049, US-006 | 2 | ~1 | T-056 | low |
| T-058 | Webhook delivery tests: mock external endpoint, assert HMAC signature, assert retry schedule, assert DLQ on exhaustion, assert audit events written | test | REQ-005, REQ-011, REQ-012 | 3 | ~2 | T-055–T-057 | low |
| **E-10 subtotal** | | | | **10** | | | |

---

### E-11 — DLQ & Circuit Breaker

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-059 | DLQ write node (C-16): insert dlq row with pipeline_state JSONB snapshot, failure_reason, status=PENDING; audit event | backend | REQ-043, US-006 | 2 | ~1 | T-033 | low |
| T-060 | DLQ API: GET /dlq (paginated, filterable by tenant/status), POST /dlq/{id}/retry (re-enters pipeline from start, idempotency 409 on re-retry), GET /dlq/{id} | backend | REQ-044, REQ-045, REQ-050, US-006 | 3 | ~2 | T-059 | low |
| T-061 | DLQ retry idempotency: check dlq.status != PENDING before re-enqueue; return 409 Conflict if already in-flight or completed | backend | REQ-050, US-006 | 1 | ~0.5 | T-060 | low |
| T-062 | Circuit breaker (C-19): per-process failure counter (asyncio.Lock), 5 failures/60s -> OPEN state; fallback to GPT-4o; alert on OPEN; reset after 60s | backend | REQ-046, REQ-047, US-006 | 5 | ~3–4 | T-041 | medium |
| T-063 | Circuit breaker + DLQ tests: 5 LLM failures trigger OPEN state, fallback invoked, both fail -> DLQ, DLQ retry idempotency (409), retry re-enters pipeline | test | REQ-043–REQ-050 | 2 | ~1 | T-059–T-062 | medium |
| **E-11 subtotal** | | | | **13** | | | |

> T-062 at 5 pts: Per-process circuit breaker state is not shared across workers — a known limitation of D-009. Implementation of fallback LLM invocation within LCEL and async state management is non-trivial.

---

### E-12 — Human Review Module

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-064 | Review queue API: GET /review (tenant-scoped list, MEDIUM items only), GET /review/{id} (detail with extracted fields + source link) | backend | REQ-014, REQ-015, US-002 | 3 | ~2 | T-017 | low |
| T-065 | Review action endpoint: POST /review/{id}/accept (save, fire webhook, write few-shot to Qdrant), POST /review/{id}/correct (save corrections, fire webhook, write corrected few-shot), POST /review/{id}/reject | backend | REQ-016, REQ-017, US-002 | 5 | ~3–4 | T-064, T-039 | medium |
| T-066 | Optimistic locking enforcement: version field check on accept/correct/reject; raise 409 StaleDataError if version mismatch | backend | REQ-019, US-002 | 2 | ~1 | T-065 | low |
| T-067 | Stale review notification: background task checks review_tasks where created_at < now()-24h and status=PENDING; fires notification via C-21 | backend | REQ-018, US-002 | 2 | ~1 | T-065 | low |
| T-068 | Notification service (C-21): pluggable notifier interface; email stub (log only at MVP); alert payload builder | backend | REQ-018, US-006 | 2 | ~1 | T-067 | low |
| T-069 | Review queue appears within 60s test: submit document, mock MEDIUM confidence, assert review_tasks row created within 60s | test | REQ-014, US-002 | 2 | ~1 | T-064 | low |
| T-070 | Review module integration tests: accept fires webhook + Qdrant write, correct persists corrections + few-shot, optimistic lock 409, tenant isolation (reviewer sees own items only) | test | REQ-015–REQ-020 | 5 | ~3–4 | T-064–T-068 | medium |
| **E-12 subtotal** | | | | **21** | | | |

> T-065 at 5 pts: the accept/correct path touches webhook delivery, Qdrant write, audit log, and document status update — four side effects in one transaction boundary. Risk of partial failure needs careful handling.

---

### E-13 — Audit Service

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-071 | Audit service (C-07): append_event() function with tenant_id, document_id, event_type, actor, payload_hash (SHA-256 of payload JSON); called synchronously from all modules | backend | REQ-036, REQ-037, US-005 | 3 | ~2 | T-012 | low |
| T-072 | Audit export API: GET /audit/export?format=ndjson|csv&start=&end= (90d range), streaming response, <30s for 90d window | backend | REQ-038, US-005 | 3 | ~2 | T-071 | low |
| T-073 | Audit append-only test: attempt UPDATE + DELETE on audit_log rows, assert PG trigger raises exception; test SHA-256 hash integrity | test | REQ-037, US-005 | 2 | ~1 | T-071, T-011 | low |
| T-074 | Audit export test: generate 1000 rows, export NDJSON + CSV, assert correct format, assert <30s, assert tenant scoping | test | REQ-038, US-005 | 2 | ~1 | T-072 | low |
| **E-13 subtotal** | | | | **10** | | | |

---

### E-14 — GDPR & Retention

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-075 | GDPR erasure endpoint: DELETE /documents/{id}: cancel in-flight pipeline (set is_cancelled), hard-delete file + extraction_results + pii fields, delete Qdrant vectors, write tombstone to audit_log | backend | REQ-039, REQ-041, US-005 | 8 | ~1 week | T-036, T-039 | high |
| T-076 | GDPR erasure Admin module wiring (C-05): orchestrator service that sequences pipeline cancel -> PG delete -> Qdrant delete -> tombstone atomically (compensating txn on partial failure) | backend | REQ-039, REQ-041, US-005 | 5 | ~3–4 | T-075 | high |
| T-077 | Retention purge cron job (C-22): nightly cron, per-tenant retention_days, delete expired documents + extraction_results + vectors; log purge event to audit_log; use ocr_admin role to bypass RLS | backend | REQ-040, US-005 | 3 | ~2 | T-071, T-039 | low |
| T-078 | GDPR erasure tests: erasure of at-rest doc (no in-flight), erasure of in-flight doc (pipeline cancelled), tombstone present after erasure, Qdrant vectors deleted, PII fields gone | test | REQ-039, REQ-041 | 3 | ~2 | T-075, T-076 | high |
| T-079 | Retention purge test: insert docs with expired retention_days, run purge job, assert deleted from PG + Qdrant, audit log entry present | test | REQ-040 | 2 | ~1 | T-077 | low |
| **E-14 subtotal** | | | | **21** | | | |

> T-075 at 8 pts: GDPR in-flight erasure is the highest-risk task. It requires: (1) atomic pipeline cancellation across async workers, (2) PG checkpoint row deletion, (3) Qdrant vector deletion, (4) tombstone write — all without leaving PII behind on partial failure. This may need a spike (SP-003).

---

### E-15 — Observability & Alerts

| Task ID | Description | Layer | REQ/Story | Points | Days (likely) | Depends on | Risk |
|---------|-------------|-------|-----------|--------|--------------|------------|------|
| T-080 | Prometheus metrics (C-20): counter/histogram instrumentation for ingestion rate, pipeline latency, DLQ rate, error rate, LLM calls; /metrics endpoint via prometheus-fastapi-instrumentator | backend | REQ-042, REQ-048, US-006 | 3 | ~2 | T-001 | low |
| T-081 | Alert rules: DLQ>50/5min, circuit breaker OPEN, p95>30s, error rate>5%; Prometheus alert rules YAML or alertmanager config | infra | REQ-048, US-006 | 2 | ~1 | T-080 | low |
| T-082 | LLM latency + cost metrics: per-call histogram (model, tenant), token usage counter; circuit breaker state gauge | backend | REQ-046, US-006 | 2 | ~1 | T-080 | low |
| T-083 | Structured log assertions: verify PII fields not present in logs for any pipeline path; verify tenant_id and document_id present in all log lines | test | REQ-053, REQ-031 | 2 | ~1 | T-005, T-080 | low |
| T-084 | Observability integration test: run a full pipeline invocation, assert /metrics has expected counters incremented, assert Prometheus histogram populated | test | REQ-042 | 2 | ~1 | T-080 | low |
| **E-15 subtotal** | | | | **11** | | | |

---

## Spikes Required

| Spike ID | Question to Answer | Time-box | Blocking | Depends |
|----------|-------------------|---------|---------|---------|
| SP-001 | LangGraph checkpoint-postgres recovery semantics: does re-running a node with an existing checkpoint correctly resume vs. re-execute? What happens to side effects (LLM calls) on replay? | 2 days | T-034 | T-033 |
| SP-002 | LlamaParse cloud API: rate limits, latency at 2-page PDF, error response structure, actual p95; validate fallback path with pdfplumber | 1 day | T-038 | none |
| SP-003 | GDPR in-flight erasure atomicity: design compensating transaction pattern for cancel -> PG delete -> Qdrant delete -> tombstone; test partial failure recovery | 1 day | T-075, T-076 | T-036 |
| SP-004 | RLS correctness validation: write an adversarial test suite that probes all 10 RLS-enabled tables for cross-tenant data leakage under various query patterns | 1 day | T-010, T-014 | T-009 |

---

## Total Estimate

| Epic | Points |
|------|--------|
| E-01 Foundation & Infrastructure | 21 |
| E-02 Data Layer & Migrations | 21 |
| E-03 Auth & Multi-Tenancy | 18 |
| E-04 Ingest API | 11 |
| E-05 Schema Registry | 16 |
| E-06 LangGraph Pipeline Core | 23 |
| E-07 Extraction + RAG | 22 |
| E-08 Guardrails | 14 |
| E-09 Confidence Scoring & Routing | 10 |
| E-10 Webhook Delivery | 10 |
| E-11 DLQ & Circuit Breaker | 13 |
| E-12 Human Review Module | 21 |
| E-13 Audit Service | 10 |
| E-14 GDPR & Retention | 21 |
| E-15 Observability & Alerts | 11 |
| **Spikes (4 × ~1.5 days avg)** | **8** |
| **GRAND TOTAL** | **250** |

| Scenario | Points | Calendar Weeks (2 engineers, velocity 20 pts/sprint, 2-week sprints) |
|---------|--------|----------------------------------------------------------------------|
| Optimistic | 200 | 5 sprints (10 weeks) — all spikes resolve quickly, no scope creep |
| **Likely** | **250** | **6.25 sprints — rounds to 6 sprints (12 weeks)** |
| Pessimistic | 310 | 8 sprints (16 weeks) — LangGraph checkpoint recovery and GDPR erasure both require rework |

> **Note:** The product spec targets 4 sprints (8 weeks) for MVP. At 20 pts/sprint velocity with 2 engineers, 4 sprints = 80 pts. The full backlog is 250 pts — this requires either 3 engineers, a velocity of ~63 pts/sprint with 2 engineers (unrealistic), or scope reduction. Recommended resolution: (a) increase to 3 engineers (3 × 10 = ~30 pts/sprint x 8 sprints = 240 pts — feasible), or (b) defer E-05 Schema Registry (16 pts) and E-12 Human Review (21 pts) to Phase 2. This decision must be made at Sprint 0.

---

## Sprint Plan

### Assumed Team
- **3 engineers**: 1 senior (lead, owns pipeline and security), 1 mid (data layer and APIs), 1 mid-junior (tests, infra, observability)
- **Velocity**: 30 story points per sprint (3 × 10 pts, conservative for new codebase)
- **Sprint duration**: 2 weeks
- **Total capacity**: 4 sprints × 30 pts = 120 pts (feature work)

> With 3 engineers at 30 pts/sprint over 4 sprints = 120 pts of feature work. The full backlog is 250 pts, which does not fit in 4 sprints at this velocity. The plan below prioritizes the core extraction pipeline (US-001 + US-004 + US-006) in Sprints 1–3, and adds review queue (US-002) and audit/GDPR (US-005) in Sprint 4 and Phase 2. This matches the MVP definition in the product spec.

---

### Sprint 1 — Foundation, Data Layer, Auth (Goal: "runnable skeleton with auth and database ready")
**Goal:** Environment running, all migrations applied, auth working end-to-end, RLS verified, developer can run a request that is authenticated and tenant-scoped.
**Demoable outcome:** POST /api/v1/extract returns 401 without valid JWT, 202 with valid JWT (queues but no pipeline yet); cross-tenant data isolation verified by test suite.

| Task | Points | Assignee hint |
|------|--------|---------------|
| T-001 Project scaffold | 3 | lead |
| T-002 Docker Compose | 2 | mid-junior |
| T-003 SQLAlchemy async engine | 2 | mid |
| T-004 Worker pool | 3 | lead |
| T-005 Structured logging | 3 | mid-junior |
| T-006 Alembic init | 2 | mid |
| T-008 CI pipeline | 3 | mid-junior |
| T-009 Migration 001_initial_schema | 5 | mid |
| T-010 Migration 002_rls_policies | 3 | mid |
| SP-004 Spike: RLS adversarial tests | 2 | lead |
| **Sprint 1 total** | **28** | |

Overflow to Sprint 2: T-011, T-012, T-013

---

### Sprint 2 — Auth, Ingest API, Schema Registry, Pipeline Foundation (Goal: "documents can be submitted and pipeline starts")
**Goal:** Full auth middleware, PII encryption, document ingest to 202, schema CRUD, LangGraph graph defined with PG checkpoint; parse node exercisable in isolation.
**Demoable outcome:** Authenticated tenant submits a PDF, gets 202 with document_id, pipeline starts executing (parse node runs), document status transitions to IN_PROGRESS.

| Task | Points | Assignee hint |
|------|--------|---------------|
| T-011 Migration 003_audit_triggers | 3 | mid |
| T-012 SQLAlchemy ORM models | 5 | mid |
| T-013 Pydantic v2 schemas | 3 | mid |
| T-014 RLS integration tests | 2 | lead |
| T-015 JWT RS256 middleware | 3 | lead |
| T-016 API key auth | 3 | lead |
| T-017 Tenant context propagation | 3 | lead |
| T-018 PII encryption service | 5 | lead |
| T-019 Rate limiting middleware | 2 | mid |
| SP-001 Spike: LangGraph checkpoint recovery | 2 | lead |
| **Sprint 2 total** | **31** | |

Overflow to Sprint 3: T-020, T-021..T-025 (Ingest API), T-026..T-031 (Schema Registry), T-032..T-037 (Pipeline Core)

> Sprint 2 is intentionally heavy on the lead engineer for security-critical components. PII encryption (T-018) and the LangGraph spike (SP-001) are the riskiest items.

---

### Sprint 3 — Full Pipeline: Parse, Extract, RAG, Guardrails, Confidence, Routing, Webhook, DLQ (Goal: "invoice goes in, result comes out via webhook")
**Goal:** End-to-end STP pipeline: ingest -> parse (LlamaParse) -> guardrails -> extract (Claude + RAG) -> confidence -> route -> webhook. DLQ and circuit breaker wired. Full E2E happy-path test passing.
**Demoable outcome:** Submit a real 2-page invoice PDF, receive HMAC-signed webhook with extracted JSON (invoiceNumber, invoiceDate, vendorName, totalAmount, currency) within 15s p95. DLQ demo for LOW confidence doc.

| Task | Points | Assignee hint |
|------|--------|---------------|
| T-020 Auth integration tests | 2 | mid-junior |
| T-021 POST /extract endpoint | 3 | mid |
| T-022 File storage adapter | 2 | mid |
| T-023 Document record + enqueue | 2 | mid |
| T-024 Dry-run flag | 2 | mid |
| T-025 Ingest tests | 2 | mid-junior |
| T-032 ExtractionState TypedDict | 2 | lead |
| T-033 LangGraph graph builder | 5 | lead |
| T-034 PG checkpoint setup | 5 | lead |
| SP-002 Spike: LlamaParse cloud | 1 | mid |
| T-038 LlamaParse client | 5 | mid |
| **Sprint 3 total** | **31** | |

Overflow to Sprint 4: T-035..T-037 (pipeline worker, GDPR cancel, crash test), T-039..T-044 (RAG), T-045..T-054 (guardrails, confidence, routing), T-055..T-063 (webhook, DLQ, breaker)

---

### Sprint 4 — Review Queue, Audit, GDPR, Observability (Goal: "MVP feature-complete for pilot launch")
**Goal:** Human review queue, audit trail, GDPR erasure (at-rest), Prometheus metrics, alerts wired. All MUST requirements covered. Pilot tenant can use the platform end-to-end.
**Demoable outcome:** MEDIUM-confidence invoice appears in review queue; reviewer edits and accepts; webhook fires with corrections; audit log shows full trace; GDPR erasure request deletes PII and tombstones. /metrics shows pipeline latency histogram.

| Task | Points | Assignee hint |
|------|--------|---------------|
| T-035 Pipeline worker | 3 | lead |
| T-036 GDPR cancellation flag | 5 | lead |
| T-039 Qdrant service wrapper | 3 | mid |
| T-040 RAG few-shot retrieval | 3 | mid |
| T-041 LangChain LCEL extraction | 5 | lead |
| T-042 Extraction result persistence | 2 | mid |
| T-045 Guardrail base | 2 | mid-junior |
| T-046 Injection detection | 3 | mid |
| T-051 Confidence scorer | 5 | lead |
| T-052 Route node | 2 | mid-junior |
| **Sprint 4 total** | **33** | |

> Sprint 4 is over-capacity (33 vs 30) — T-037 crash recovery test and remaining tests from E-07/E-08/E-09 slip to Sprint 5 (post-MVP hardening sprint). The GDPR in-flight erasure (T-075, T-076) is deferred to Sprint 5 due to complexity; at-rest GDPR is Sprint 4.

---

### Sprint 5 (Hardening Sprint) — Webhook, DLQ, Review, Observability, GDPR In-Flight
**Goal:** All remaining pipeline tasks, review module complete, full GDPR (in-flight), observability complete, integration test suite green.
**Note:** This sprint brings the full backlog to completion and is labeled "hardening" — it is effectively Sprint 5 of the 4-sprint MVP, driven by the realistic estimate.

Selected deferred tasks (not exhaustive):
T-047..T-050 (guardrails), T-053..T-054 (thresholds/routing tests), T-055..T-063 (webhook, DLQ, breaker), T-064..T-070 (review module), T-071..T-074 (audit), T-075..T-079 (GDPR+retention), SP-003 (GDPR spike), T-080..T-084 (observability), T-026..T-031 (schema registry)

**Estimated points in Sprint 5+:** ~130 points across 2 additional sprints (Sprints 5–6) at 30 pts/sprint with 3 engineers.

---

## Critical Path

Tasks that, if delayed, delay the whole delivery:

```
T-001 (scaffold)
  → T-003 (SQLAlchemy engine)
    → T-006 (Alembic init)
      → T-009 (initial schema migration)
        → T-010 (RLS policies)
          → T-012 (ORM models)
            → T-015 (JWT middleware)
              → T-017 (tenant context)
                → T-018 (PII encryption)
                  → T-021 (ingest endpoint)
                    → T-023 (document record + enqueue)
                      → T-032 (ExtractionState)
                        → T-033 (LangGraph graph)
                          → T-034 (PG checkpoint)  <-- SPIKE SP-001 feeds here
                            → T-035 (pipeline worker)
                              → T-038 (LlamaParse)  <-- SPIKE SP-002 feeds here
                                → T-040 (RAG retrieval)
                                  → T-041 (LCEL extraction)
                                    → T-051 (confidence scorer)
                                      → T-052 (route node)
                                        → T-055 (webhook builder)
                                          → T-056 (webhook delivery)
                                            → [MVP STP Complete]
```

**Critical path length: 20 tasks** (excluding spikes). Any task on this path delayed by 1 sprint = MVP delayed by 1 sprint.

Secondary critical path (GDPR / compliance launch gate):
```
T-036 (GDPR cancel) → SP-003 (GDPR spike) → T-075 (erasure endpoint) → T-076 (orchestrator) → T-078 (erasure tests)
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| LangGraph checkpoint-postgres recovery semantics unclear (SP-001) | High | High | Time-box 2-day spike in Sprint 2; if unresolved, implement simpler restart-from-scratch fallback with idempotent nodes |
| LlamaParse cloud API latency / rate limits blow 15s p95 SLA (I-003) | Medium | High | SP-002 spike in Sprint 3 day 1; contract pdfplumber fallback in same sprint; negotiate LlamaParse dedicated plan |
| GDPR in-flight erasure partial failure leaves PII behind (REQ-041) | Medium | Critical | SP-003 spike; compensating transaction design; accept at-rest only for pilot launch if unresolved |
| RLS policy misconfiguration leaks cross-tenant data (REQ-029) | Medium | Critical | SP-004 adversarial test suite in Sprint 1; security review before any PII tenant onboarded |
| Cross-tenant Qdrant guard failure exposes few-shot examples (REQ-030, REQ-033) | Low | Critical | Post-query assertion in C-18 (T-039, T-044); unit tests on every query path; CRITICAL log on omission |
| LLM provider DPA not signed before pilot with PII data (I-001) | High | High | Blocking open issue — legal track must run parallel; use synthetic data for all pre-pilot testing |
| Confidence algorithm F1 < 90% on real invoices (metric) | Medium | High | I-002 (required fields) must be confirmed with pilot tenant before Sprint 3; run evals on seed invoices |
| PII encryption key management not designed (DM-001, T-018) | Medium | High | Design key derivation scheme in Sprint 2 spike or T-018; document key rotation plan |
| asyncio circuit breaker state not shared across workers (D-009) | Low | Medium | Document known limitation; for 1 pilot tenant, single-process deployment mitigates in MVP |
| Schema versioning + in-flight doc pinning race condition (REQ-025) | Low | Medium | Optimistic lock on schema.current_version; test in T-030 |

---

## Definition of Done (Applied to Every Task)

- [ ] Unit tests written and passing (pytest-asyncio); coverage >= 80% for new code
- [ ] Integration test covering the happy path and at least one error case
- [ ] For any database change: Alembic migration written and verified (upgrade + downgrade)
- [ ] RLS enforced: if task touches a tenant-scoped table, a cross-tenant isolation test is included
- [ ] PII handling: no PII fields appear in logs; AES-256-GCM encryption applied where required
- [ ] Audit event: every state-changing operation writes an audit_log entry (event_type, actor, payload_hash)
- [ ] Prometheus metric updated where applicable (counter incremented, histogram observed)
- [ ] Structured JSON log line emitted with tenant_id + document_id at every pipeline node entry/exit
- [ ] No secrets or credentials in code; all config via pydantic-settings / environment variables
- [ ] Code review approved by at least one other engineer
- [ ] ruff lint + mypy type-check passing (no new errors)
- [ ] GDPR note: if task processes or stores PII fields, GDPR erasure path is identified and tracked

---

## Open Questions (Blocking Sprint Planning)

| ID | Question | Impact | Owner |
|----|---------|--------|-------|
| I-001 | LLM provider DPA signed? | Cannot onboard PII pilot tenant | Legal/PM |
| I-002 | Invoice required field set confirmed with pilot? | Affects confidence scorer (T-051) | PM / Pilot Tenant |
| I-003 | LlamaParse cloud vs self-hosted final decision? | T-038 implementation path | Architect |
| DM-001 | webhook_secret encrypted at rest? | T-016 implementation, security review | Lead Engineer |
| DM-002 | File storage: local (dev only) vs S3 from day 1? | T-022 scope and effort | Architect |
| DM-004 | Qdrant vector dimension: 1536 (OpenAI) vs 768? | T-039, T-040 embedding model selection | Lead Engineer |
