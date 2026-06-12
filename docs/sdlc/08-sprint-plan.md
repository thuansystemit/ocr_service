# Sprint Plan — Enterprise OCR / Document-Extraction Platform (MVP)
**Date:** 2026-06-11  **Author:** @planner  **Status:** COMMITTED
**Sources:** `docs/sdlc/02-requirements.md`, `docs/sdlc/05-estimation.md`

---

## Confirmed Scope Decision

12-week / 6-sprint timeline at FULL MVP scope.
Team: 3 engineers (1 Senior/Lead, 1 Mid Backend, 1 Mid-Junior/Infra).
Velocity: 30 story points per 2-week sprint.
Total committed: ~250 points.
E-05 Schema Registry and E-12 Human Review UI are INCLUDED in this plan (not deferred).

---

## Sprint Goal Overview

| Sprint | Dates (Week) | Goal | Milestone |
|--------|-------------|------|-----------|
| Sprint 1 | Wk 1–2 | Foundation, data layer, RLS green | Skeleton auth'd request in DB |
| Sprint 2 | Wk 3–4 | Auth complete, PII encryption, pipeline skeleton | LangGraph graph compilable |
| Sprint 3 | Wk 5–6 | Ingest API + STP happy path (parse → webhook) | STP DEMO — invoice in, webhook out |
| Sprint 4 | Wk 7–8 | Confidence + routing + DLQ + review queue + circuit breaker | Invoice-in / webhook-out pilot core |
| Sprint 5 | Wk 9–10 | Audit, GDPR (at-rest + in-flight), schema registry, guardrail hardening | Feature-complete |
| Sprint 6 | Wk 11–12 | Observability, retention purge, integration sweep, hardening | PILOT-READY / MVP handoff |

---

## Sprint 1 — Foundation, Data Layer, RLS (Weeks 1–2)

**Sprint Goal:** Developer can authenticate with a JWT or API key, submit a request that is tenant-scoped in the database, and the RLS cross-tenant leak test suite passes. Environment runs in Docker Compose. CI is green.

**Demoable Outcome:** `POST /api/v1/extract` returns 401 without a valid JWT and 202 (queued, no pipeline yet) with a valid JWT. A test proves that tenant A cannot read tenant B's rows under RLS.

### Spike This Sprint
| Spike | Effort | Blocks | Owner |
|-------|--------|--------|-------|
| SP-004 RLS adversarial test suite design | 1 day | T-010, T-014 | Lead |

### Sprint Backlog

| Task ID | Story/REQ | Description | Layer | Pts | Owner | Depends On | Status |
|---------|----------|-------------|-------|-----|-------|-----------|--------|
| T-001 | NFR | Project scaffold: FastAPI app factory, pydantic-settings, structlog env hierarchy | Infra | 3 | Lead | — | TODO |
| T-002 | NFR | Docker Compose: pg16 + qdrant + app + worker; health checks; volume mounts | Infra | 2 | Mid-Junior | T-001 | TODO |
| T-003 | NFR | SQLAlchemy 2.0 async engine + session factory; connection pool; per-request dependency | Backend | 2 | Mid | T-001 | TODO |
| T-004 | REQ-052 | asyncio.Semaphore worker pool: per-tenant semaphore map, submit/release, configurable concurrency | Backend | 3 | Lead | T-001 | TODO |
| T-005 | REQ-053, REQ-031 | Structured JSON log formatter: tenant_id, document_id, PII redaction filter ([REDACTED]) | Infra | 3 | Mid-Junior | T-001 | TODO |
| T-006 | NFR | Alembic init: async env.py, revision template, Makefile targets (upgrade/downgrade/autogenerate) | Infra | 2 | Mid | T-003 | TODO |
| T-007 | NFR | Kubernetes manifests skeleton: Deployment + HPA (app/worker), ConfigMap, Secrets template, Service, Ingress | Infra | 3 | Mid-Junior | T-002 | TODO |
| T-008 | NFR | CI pipeline: ruff lint, mypy type-check, pytest-asyncio, Docker build | Infra | 3 | Mid-Junior | T-001 | TODO |
| T-009 | REQ-029 | Alembic migration 001_initial_schema: all 11 tables, 24 indexes, UUID PKs, JSONB columns | Database | 5 | Mid | T-006 | TODO |
| T-010 | REQ-029, US-004 | Alembic migration 002_rls_policies: RLS ENABLE + CREATE POLICY for 10 tenant tables; ocr_admin bypass role | Database | 3 | Mid | T-009, SP-004 | TODO |

**Sprint 1 Total: 29 points** (1 pt under target — acceptable; T-011 carries to Sprint 2 as first item)

### Sprint 1 Acceptance Criteria
- [ ] Docker Compose `up` starts all services; all health checks pass
- [ ] `GET /health` returns 200 with service metadata
- [ ] `POST /api/v1/extract` with no JWT returns 401; with valid JWT returns 202 and a `document_id`
- [ ] RLS adversarial test: tenant B's token cannot read tenant A's `documents` rows (SP-004 result applied to T-010)
- [ ] All migrations apply cleanly (`alembic upgrade head`) and roll back cleanly (`alembic downgrade -1`)
- [ ] CI pipeline passes on first PR (ruff + mypy + pytest)
- [ ] No secrets in committed code; all config via env vars

### Sprint 1 Risk Gates
| Open Issue | Must Resolve By | Owner |
|-----------|----------------|-------|
| DM-002: local fs vs S3 scope for T-022 | End of Sprint 1 | Architect |
| DM-004: Qdrant vector dimension (1536 vs 768) | End of Sprint 1 (affects T-039) | Lead |

---

## Sprint 2 — Auth Complete, PII Encryption, LangGraph Foundation (Weeks 3–4)

**Sprint Goal:** Full auth middleware (JWT + API key) operational with tenant context propagation. PII encryption service wired. LangGraph pipeline core compiled with PG checkpoint (spike result applied). ORM models complete. Schema Registry CRUD API scaffolded.

**Demoable Outcome:** Authenticated tenant submits a document; document row appears in PG with status=PENDING; `document.pii_fields` are AES-256-GCM encrypted at rest; LangGraph graph compiles and checkpoint saver connects to PG without errors.

### Spike This Sprint
| Spike | Effort | Blocks | Owner |
|-------|--------|--------|-------|
| SP-001 LangGraph checkpoint-postgres recovery semantics | 2 days | T-034 | Lead |

### Sprint Backlog

| Task ID | Story/REQ | Description | Layer | Pts | Owner | Depends On | Status |
|---------|----------|-------------|-------|-----|-------|-----------|--------|
| T-011 | REQ-037, REQ-026 | Alembic migration 003_audit_triggers: trg_audit_no_update, trg_audit_no_delete on audit_log; schema activation gate trigger | Database | 3 | Mid | T-009 | TODO |
| T-012 | All | SQLAlchemy ORM models: all 11 tables as mapped dataclasses; relationships; optimistic lock event listener (StaleDataError → 409) | Backend | 5 | Mid | T-009 | TODO |
| T-013 | All | Pydantic v2 schemas: 16 models; model_validator for confidence thresholds | Backend | 3 | Mid | T-012 | TODO |
| T-014 | REQ-029 | RLS middleware integration tests: SET LOCAL enforcement, cross-tenant leak assertion, ocr_admin bypass | Test | 2 | Lead | T-010, T-012 | TODO |
| T-015 | REQ-028, REQ-034 | JWT RS256 middleware: extract tenant_id, populate contextvars + SET LOCAL; 401 on missing/invalid | Backend | 3 | Lead | T-012 | TODO |
| T-016 | REQ-032 | API key auth: SHA-256 hash lookup, revocation check (<100ms p95), LRU cache TTL 60s | Backend | 3 | Lead | T-012 | TODO |
| T-017 | REQ-029, US-004 | Tenant context propagation: contextvars.ContextVar, FastAPI dependency, SQLAlchemy SET LOCAL hook | Backend | 3 | Lead | T-015, T-016 | TODO |
| T-018 | REQ-031, US-004 | PII encryption service: AES-256-GCM field-level encrypt/decrypt; per-tenant key derivation; log masking decorator | Backend | 5 | Lead | T-015 | TODO |
| T-032 | REQ-052, US-001 | ExtractionState TypedDict: all fields (document_id, tenant_id, schema_id, schema_version, status, raw_text, guardrail_results, extracted_json, confidence, routing_decision, error, is_cancelled) | Backend | 2 | Lead | T-001 | TODO |

**Sprint 2 Total: 29 points** (Note: SP-001 spike = 2 days of Lead capacity, counted within T-034 prep; T-019, T-020 carry to Sprint 3 as first items)

### Sprint 2 Parallelization
- **Lead**: T-015 → T-016 → T-017 → T-018; SP-001 spike alongside T-017
- **Mid**: T-011 → T-012 → T-013 (sequential, dependent chain)
- **Mid-Junior**: T-014 (after T-010, T-012 land); support Mid with test fixtures

### Sprint 2 Acceptance Criteria
- [ ] JWT RS256 middleware: valid token succeeds, expired token returns 401, missing `tenant_id` claim returns 401
- [ ] API key: create key, use key (202), revoke key, use revoked key (401 within 100ms)
- [ ] PII field encrypted at rest in DB; log line shows `[REDACTED]` for `pii_fields` values
- [ ] LangGraph graph (`CompiledGraph`) instantiates without error; PG checkpoint table exists after `alembic upgrade head`
- [ ] SP-001 spike report: recovery semantics documented, re-execution risk identified, mitigation confirmed
- [ ] All audit trigger migration applies; attempt UPDATE on `audit_log` raises PG exception
- [ ] Auth + RLS integration tests all green in CI

### Sprint 2 Risk Gates
| Open Issue | Must Resolve By | Owner |
|-----------|----------------|-------|
| I-001: LLM provider DPA — must start legal track | End of Sprint 2 (parallel) | PM/Legal |
| DM-001: webhook_secret encryption-at-rest design | End of Sprint 2 | Lead |
| SP-001 result: LangGraph recovery path confirmed | End of Sprint 2 | Lead |

---

## Sprint 3 — Ingest API + Full STP Pipeline (Weeks 5–6)

**Sprint Goal:** End-to-end STP (straight-through processing) happy path: a real 2-page PDF goes in via the ingest API, is parsed by LlamaParse, passes guardrails, is extracted by Claude with RAG few-shot context, receives a HIGH confidence score, and fires a signed webhook — all within 15s p95.

**Demoable Outcome:** Submit a real 2-page invoice PDF. Receive a HMAC-SHA256-signed webhook payload containing `{ invoiceNumber, invoiceDate, vendorName, totalAmount, currency }` within 15 seconds. Schema Registry: create a schema draft, upload 3 seed docs, activate, submit — pipeline uses the new schema without redeployment.

### Spike This Sprint
| Spike | Effort | Blocks | Owner |
|-------|--------|--------|-------|
| SP-002 LlamaParse cloud API latency + rate limits | 1 day | T-038 | Mid |

### Sprint Backlog

| Task ID | Story/REQ | Description | Layer | Pts | Owner | Depends On | Status |
|---------|----------|-------------|-------|-----|-------|-----------|--------|
| T-019 | REQ-035 | Rate limiting middleware: per-tenant queue size check, 429 response, asyncio counter | Backend | 2 | Mid | T-017 | TODO |
| T-020 | REQ-028–034 | Auth + RLS integration tests: JWT valid/invalid/expired, API key round-trip, cross-tenant isolation | Test | 2 | Mid-Junior | T-015–T-019 | TODO |
| T-021 | REQ-001, REQ-006–008 | POST /api/v1/extract: multipart upload, 413 >50MB, 422 MIME, 422 unknown doc_type, 202+document_id within 500ms | Backend | 3 | Mid | T-017 | TODO |
| T-022 | US-001 | File storage adapter: local fs (dev), pluggable interface, async write, content-type recorded | Backend | 2 | Mid | T-021 | TODO |
| T-023 | REQ-001, REQ-052 | Document record creation + enqueue: insert documents row (PENDING), enqueue to worker pool, idempotency check | Backend | 2 | Mid | T-021, T-004 | TODO |
| T-024 | REQ-023, US-003 | Dry-run flag: is_dry_run=true skips persist + webhook, returns extraction preview | Backend | 2 | Mid | T-023 | TODO |
| T-033 | REQ-052, US-001 | LangGraph graph builder: 9 nodes (PARSE, GUARDRAIL, EXTRACT, SCORE, ROUTE, WEBHOOK, CREATE_REVIEW, DLQ_WRITE, COMPLETE), conditional edges | Backend | 5 | Lead | T-032 | TODO |
| T-034 | REQ-052 | langgraph-checkpoint-postgres: CheckpointSaver wired to async PG pool; thread_id=document_id; resume-from-checkpoint on restart (SP-001 result applied) | Backend | 5 | Lead | T-033, T-003, SP-001 | TODO |
| T-026 | REQ-021, US-003 | Schema CRUD API: POST /schemas (draft), GET /schemas/{id}, PUT /schemas/{id}, GET /schemas (list, tenant-scoped) | Backend | 3 | Mid | T-017 | TODO |
| T-025 | REQ-001–008 | Ingest API integration tests: 202 happy path, 413, 422 MIME, 422 doc_type, 500ms SLA, dry-run | Test | 2 | Mid-Junior | T-021–T-024 | TODO |

**Sprint 3 Total: 28 points** (SP-002 spike = 1 day Mid capacity; T-027–T-031 schema registry remainder and T-035, T-038 continue into Sprint 4 week 1 — see carry notes below)

> Note: T-033 (5 pts) and T-034 (5 pts) are the two heaviest items and gate the entire pipeline. Lead owns both; Mid-Junior supports with test fixture scaffolding. Sprint 3 is deliberately kept at 28 to give the Lead room for SP-002 coordination and the LangGraph integration complexity.

### Sprint 3 Parallelization
- **Lead**: T-033 → T-034 (sequential; blocks pipeline core)
- **Mid**: T-019 → T-021 → T-022 → T-023 → T-024 → T-026 (ingest + schema registry API)
- **Mid-Junior**: T-020, T-025 (tests); SP-002 spike support

### Sprint 3 Acceptance Criteria
- [ ] `POST /api/v1/extract` returns 202 with `document_id` within 500ms under load
- [ ] Oversized file (>50MB) returns 413; bad MIME type returns 422; unknown `document_type` returns 422
- [ ] LangGraph graph compiles with all 9 nodes; PG checkpoint saver persists state between invocations
- [ ] Schema CRUD: create draft schema, GET returns it; tenant B cannot see tenant A's schemas
- [ ] Dry-run: returns extraction preview JSON, no row written to `documents`, no webhook fired
- [ ] SP-002 result: LlamaParse p95 latency documented; fallback path decision confirmed

### Sprint 3 Risk Gate
| Open Issue | Must Resolve By | Owner |
|-----------|----------------|-------|
| I-002: Invoice required field set confirmed with pilot tenant | End of Sprint 3 (gates T-051 in Sprint 4) | PM / Pilot Tenant |
| I-003: LlamaParse cloud vs self-hosted final decision | Sprint 3 Day 1 (before T-038 starts) | Architect |
| I-007: Per-document pipeline timeout (60s) benchmark | Sprint 3 (measured during LangGraph integration) | Lead |

---

**Milestone M-1 (End of Sprint 3):** STP happy path demoable — invoice PDF in, signed webhook out, schema activation without redeployment.

---

## Sprint 4 — Extraction + Confidence + Routing + DLQ + Review Queue (Weeks 7–8)

**Sprint Goal:** Complete the full extraction pipeline (LlamaParse → Qdrant RAG → LangChain LCEL → confidence scorer → router → webhook → DLQ). Human review queue operational. Circuit breaker wired. A MEDIUM-confidence document appears in the review queue and can be accepted/corrected, firing a webhook with the reviewer's edits.

**Demoable Outcome:** (1) HIGH-confidence invoice → webhook fires. (2) MEDIUM-confidence invoice → review queue, reviewer accepts → corrected webhook fires + few-shot written to Qdrant. (3) Inject 5 LLM failures → circuit breaker opens, fallback GPT-4o engages, alert fires.

### Sprint Backlog

| Task ID | Story/REQ | Description | Layer | Pts | Owner | Depends On | Status |
|---------|----------|-------------|-------|-----|-------|-----------|--------|
| T-035 | REQ-052, US-001 | Pipeline async worker: queue consume, graph invoke with initial state, exception handling, document.status update | Backend | 3 | Lead | T-033, T-004 | TODO |
| T-038 | REQ-002, US-001 | LlamaParse cloud client: async HTTP, retry 3×, pdfplumber fallback on 5xx/timeout, pytesseract fallback (SP-002 result applied) | Backend | 5 | Mid | T-033, SP-002 | TODO |
| T-039 | REQ-030, REQ-033 | Qdrant service wrapper: async client, mandatory tenant_id filter injection, post-query assertion (CRITICAL if absent), vector upsert | Backend | 3 | Mid | T-001 | TODO |
| T-040 | REQ-033, US-001 | RAG few-shot retrieval: embed input text, query Qdrant (tenant_id + schema_id filters), top-K examples, prompt builder | Backend | 3 | Mid | T-039 | TODO |
| T-041 | REQ-002, REQ-003 | LangChain LCEL extraction chain: BaseChatModel abstraction, primary Claude claude-sonnet-4-6, fallback GPT-4o, structured output (Pydantic), few-shot prompt template | Backend | 5 | Lead | T-040 | TODO |
| T-051 | REQ-003, REQ-004 | Confidence scorer: min(llm_self, completeness, semantic) × guardrail_multiplier; completeness = required fields present/total; semantic = cosine similarity vs seed examples | Backend | 5 | Lead | T-041, T-048 | TODO |
| T-052 | REQ-003, REQ-009, REQ-010 | Route node: HIGH(≥0.85)→WEBHOOK, MEDIUM(≥0.60)→CREATE_REVIEW, LOW(<0.60)→DLQ_WRITE; update documents.routing_decision | Backend | 2 | Mid-Junior | T-051 | TODO |
| T-064 | REQ-014, REQ-015, US-002 | Review queue API: GET /review (tenant-scoped, MEDIUM items), GET /review/{id} (detail + source link) | Backend | 3 | Mid | T-017 | TODO |
| T-055 | REQ-011, US-001 | Webhook payload builder: HMAC-SHA256 sign with tenant.webhook_secret; X-OCR-Signature header; serialize extraction result | Backend | 2 | Mid-Junior | T-041 | TODO |

**Sprint 4 Total: 31 points** (1 pt over; acceptable — T-062 circuit breaker carries to Sprint 5 week 1 as first item)

### Sprint 4 Parallelization
- **Lead**: T-035 → T-041 → T-051 (critical path — pipeline worker → extraction → confidence)
- **Mid**: T-038 → T-039 → T-040 → T-064 (LlamaParse, Qdrant, RAG, review API — can parallelize T-064 once T-017 is stable)
- **Mid-Junior**: T-052, T-055 (routing node + webhook builder, unblocked after T-051/T-041 land)

### Sprint 4 Acceptance Criteria
- [ ] End-to-end: 2-page invoice PDF submitted → pipeline completes → HIGH confidence → webhook fires with HMAC signature within 15s p95
- [ ] MEDIUM confidence document appears in `review_tasks` table within 60 seconds of ingest
- [ ] `GET /review` returns only the authenticated tenant's review items (no cross-tenant bleed)
- [ ] `GET /review/{id}` returns extracted fields and source document link
- [ ] Confidence scorer: boundary tests pass (0.85 → WEBHOOK, 0.84 → review, 0.60 → review, 0.59 → DLQ)
- [ ] Webhook payload has valid HMAC-SHA256 signature verifiable with tenant `webhook_secret`
- [ ] Pipeline worker recovers from restart using PG checkpoint (T-037 gate)

### Sprint 4 Risk Gate
| Open Issue | Must Resolve By | Owner |
|-----------|----------------|-------|
| I-002: Invoice field set (gates T-051 completeness score) | Sprint 4 Day 1 | PM |
| I-005: WARN confidence multiplier (0.8×) validated against evals | Sprint 4 | Lead |
| I-001: LLM provider DPA progress check | Sprint 4 review | PM/Legal |

---

**Milestone M-2 (End of Sprint 4):** Invoice-in / webhook-out pilot core complete — extraction pipeline fully wired, review queue operational, HIGH/MEDIUM/LOW routing working.

---

## Sprint 5 — Guardrails, Webhook Hardening, DLQ, Circuit Breaker, Audit, GDPR At-Rest, Schema Registry Complete (Weeks 9–10)

**Sprint Goal:** Platform is feature-complete for non-GDPR-in-flight use cases. Guardrails fully wired (injection detection + quality). Webhook retry + exhaustion DLQ wired. Circuit breaker operational. Audit service and export API complete. GDPR erasure for at-rest documents. Schema Registry versioning and seed management complete.

**Demoable Outcome:** (1) Inject a prompt-injection string → BLOCK → DLQ. (2) Webhook endpoint goes down → 5 retry attempts → DLQ with last HTTP status. (3) DELETE /documents/{id} → PII hard-deleted + tombstone in audit log. (4) Audit export returns 1000-row NDJSON in <30s. (5) Schema version incremented on activation; in-flight doc pins old version.

### Spike This Sprint
| Spike | Effort | Blocks | Owner |
|-------|--------|--------|-------|
| SP-003 GDPR in-flight erasure compensating transaction design | 1 day | T-075, T-076 | Lead |

### Sprint Backlog

| Task ID | Story/REQ | Description | Layer | Pts | Owner | Depends On | Status |
|---------|----------|-------------|-------|-----|-------|-----------|--------|
| T-062 | REQ-046, REQ-047 | Circuit breaker: per-process failure counter (asyncio.Lock), 5 failures/60s → OPEN; fallback GPT-4o; alert on OPEN; reset after 60s | Backend | 5 | Lead | T-041 | TODO |
| T-045 | US-001 | Guardrail base interface: abstract GuardrailBase with run() → GuardrailResult; PASS/WARN/BLOCK enum; pipeline multiplier aggregation | Backend | 2 | Mid-Junior | T-032 | TODO |
| T-046 | REQ-013 | Injection detection guardrail: regex + heuristic scan of raw_text; BLOCK on detection | Backend | 3 | Mid | T-045 | TODO |
| T-047 | US-001 | Text quality guardrail: empty text, min length, character entropy check; WARN on low quality | Backend | 2 | Mid-Junior | T-045 | TODO |
| T-048 | REQ-013 | Guardrail pipeline node: run all guardrails, collect guardrail_reports, compute aggregate multiplier, BLOCK→DLQ, WARN→multiply confidence | Backend | 3 | Mid | T-046, T-047 | TODO |
| T-056 | REQ-005, REQ-012 | Webhook delivery node: async HTTP POST with timeout; record to webhook_deliveries; retry [1,5,30,120,600]s exponential backoff | Backend | 3 | Mid | T-055 | TODO |
| T-057 | REQ-012, REQ-049 | Webhook exhaustion → DLQ: after 5 failed attempts, write to dlq with last_http_status; EXHAUSTED audit event | Backend | 2 | Mid-Junior | T-056 | TODO |
| T-059 | REQ-043 | DLQ write node: insert dlq row with pipeline_state JSONB snapshot, failure_reason, status=PENDING; audit event | Backend | 2 | Mid-Junior | T-033 | TODO |
| T-060 | REQ-044, REQ-045, REQ-050 | DLQ API: GET /dlq (paginated, filterable by tenant/status), POST /dlq/{id}/retry (re-enters pipeline), GET /dlq/{id} | Backend | 3 | Mid | T-059 | TODO |
| T-071 | REQ-036, REQ-037 | Audit service: append_event() with tenant_id, document_id, event_type, actor, payload_hash (SHA-256); called from all modules | Backend | 3 | Lead | T-012 | TODO |

**Sprint 5 Total: 28 points** (SP-003 spike = 1 day Lead capacity absorbed; T-027, T-028, T-029 schema registry and remaining tests carry to Sprint 6)

> Sprint 5 deliberately leaves 2 pts of buffer to absorb SP-003 spike and any carryover from Sprint 4.

### Sprint 5 Parallelization
- **Lead**: T-062 (circuit breaker) → T-071 (audit service) → SP-003 (GDPR spike, late in sprint)
- **Mid**: T-046 → T-048 → T-056 → T-060 (guardrails → webhook → DLQ API)
- **Mid-Junior**: T-045 → T-047 → T-057 → T-059 (base interfaces + simple pipeline nodes)

### Sprint 5 Acceptance Criteria
- [ ] Prompt-injection pattern in document body → BLOCK guardrail → document enters DLQ with `failure_reason=INJECTION_DETECTED`
- [ ] Quality-check WARN: guardrail_multiplier reduces confidence score by configured factor
- [ ] Webhook endpoint returns 5xx for 5 attempts → document written to DLQ with `last_http_status`
- [ ] DLQ list API: paginated, returns only calling tenant's items
- [ ] DLQ retry endpoint re-enqueues document; 409 returned if already in-flight
- [ ] Circuit breaker: 5 LLM failures within 60s → OPEN state; fallback GPT-4o engaged; alert metric emitted
- [ ] Audit: `append_event()` writes row; UPDATE/DELETE on `audit_log` raises PG exception
- [ ] SP-003 spike report: compensating transaction pattern documented and approved

### Sprint 5 Risk Gate
| Open Issue | Must Resolve By | Owner |
|-----------|----------------|-------|
| I-001: LLM DPA signed (hard gate for PII tenant pilot) | End of Sprint 5 | PM/Legal |
| SP-003 result: GDPR in-flight compensating txn design confirmed | End of Sprint 5 | Lead |

---

## Sprint 6 — GDPR In-Flight, Schema Registry Complete, Retention Purge, Review Module Complete, Observability, Integration Sweep, Hardening (Weeks 11–12)

**Sprint Goal:** MVP hardened and pilot-ready. GDPR in-flight erasure (cancel pipeline + hard-delete + tombstone) complete. Full schema registry (versioning, seed management, activation gate). Review module actions (accept/correct/reject with webhook + Qdrant few-shot write). Observability: Prometheus metrics, alert rules, PII-clean log assertions. Full integration test sweep: all Gherkin scenarios pass.

**Demoable Outcome:** (1) GDPR erasure of an in-flight document: pipeline halts, PII purged from PG + Qdrant, tombstone in audit log, erasure confirmed within 60s. (2) Reviewer accepts a MEDIUM document: webhook fires, correction written to Qdrant as new few-shot example. (3) `/metrics` endpoint shows pipeline latency histogram, DLQ counter, LLM call counters. (4) Schema v2 activated while v1 doc is in-flight: v1 doc completes on v1; new submission uses v2.

### Sprint Backlog

| Task ID | Story/REQ | Description | Layer | Pts | Owner | Depends On | Status |
|---------|----------|-------------|-------|-----|-------|-----------|--------|
| T-027 | REQ-025, US-003 | Schema versioning: version increment on activate; schema_versions row on each activation; in-flight docs pin schema_version | Backend | 3 | Mid | T-026 | TODO |
| T-028 | REQ-022, REQ-027 | Seed example management: POST /schemas/{id}/seeds, validate, store to Qdrant (tenant-scoped), increment seed_count | Backend | 3 | Mid | T-026, T-039 | TODO |
| T-029 | REQ-024, REQ-026 | Activation gate: block if seed_count<3; DRAFT→ACTIVE→DEPRECATED transitions; PG trigger + API-layer check | Backend | 2 | Mid | T-028 | TODO |
| T-065 | REQ-016, REQ-017 | Review action endpoint: POST /review/{id}/accept + /correct (save, fire webhook, write few-shot to Qdrant) + /reject | Backend | 5 | Lead | T-064, T-039 | TODO |
| T-066 | REQ-019 | Optimistic locking: version field check on accept/correct/reject; 409 StaleDataError on version mismatch | Backend | 2 | Mid-Junior | T-065 | TODO |
| T-067 | REQ-018 | Stale review notification: background task checks review_tasks created >24h ago with status=PENDING; fires via C-21 | Backend | 2 | Mid-Junior | T-065 | TODO |
| T-068 | REQ-018 | Notification service: pluggable notifier interface; email stub (log-only at MVP) | Backend | 2 | Mid-Junior | T-067 | TODO |
| T-075 | REQ-039, REQ-041 | GDPR erasure endpoint: DELETE /documents/{id}: cancel in-flight pipeline (is_cancelled), hard-delete file + extraction_results + PII, delete Qdrant vectors, write tombstone (SP-003 result applied) | Backend | 8 | Lead | T-036, T-039, SP-003 | TODO |
| T-080 | REQ-042, REQ-048 | Prometheus metrics: counter/histogram for ingestion rate, pipeline latency, DLQ rate, error rate, LLM calls; /metrics endpoint | Backend | 3 | Mid-Junior | T-001 | TODO |

**Sprint 6 Total: 30 points** (exactly on target)

> The remaining tasks (T-036 GDPR cancel flag, T-037 crash recovery test, T-042–T-044, T-049–T-050, T-053–T-054, T-058, T-061, T-063, T-069–T-070, T-072–T-074, T-076–T-079, T-081–T-084, T-030–T-031, T-053) are integration tests, configuration tasks, and test suites. These are scheduled as the final week's integration sweep. See "Integration Test Sweep" below.

### Sprint 6 Integration Test Sweep (Week 12, all engineers)

The following test tasks and low-complexity configuration tasks are grouped as the final integration and hardening push. Estimated at ~35 points total; completed in parallel across the team in Week 12 with the understanding that some will slip to a post-MVP patch sprint if blocked by upstream tasks.

| Task ID | Description | Pts | Owner |
|---------|-------------|-----|-------|
| T-036 | GDPR cancellation flag: is_cancelled check between every node; purge checkpoint on cancel | 5 | Lead |
| T-042 | Extraction result persistence: insert extraction_results, encrypt pii_fields, hash | 2 | Mid |
| T-043 | LlamaParse integration tests: mock cloud, retry on 5xx, fallback assertions | 2 | Mid-Junior |
| T-044 | Cross-tenant RAG isolation test | 2 | Lead |
| T-049 | Guardrail reports persistence | 1 | Mid-Junior |
| T-050 | Guardrail unit + integration tests | 3 | Mid-Junior |
| T-053 | Configurable confidence thresholds per schema | 1 | Mid |
| T-054 | Confidence + routing tests: boundary conditions, missing required field, WARN multiplier | 2 | Mid-Junior |
| T-058 | Webhook delivery tests: HMAC assert, retry schedule, DLQ on exhaustion, audit events | 3 | Mid-Junior |
| T-061 | DLQ retry idempotency: 409 on re-retry of in-flight | 1 | Mid |
| T-063 | Circuit breaker + DLQ tests | 2 | Mid-Junior |
| T-069 | Review queue 60s SLA test | 2 | Mid-Junior |
| T-070 | Review module integration tests: accept/correct/reject, optimistic lock, tenant isolation | 5 | Mid |
| T-072 | Audit export API: GET /audit/export (NDJSON/CSV, streaming, <30s) | 3 | Mid |
| T-073 | Audit append-only test + hash integrity | 2 | Mid-Junior |
| T-074 | Audit export test: 1000 rows, format, SLA, tenant scope | 2 | Mid-Junior |
| T-076 | GDPR erasure orchestrator: compensating txn (cancel → PG delete → Qdrant delete → tombstone) | 5 | Lead |
| T-077 | Retention purge cron job: nightly, per-tenant retention_days, ocr_admin bypass | 3 | Mid |
| T-078 | GDPR erasure tests: at-rest, in-flight, tombstone, Qdrant, PII fields gone | 3 | Lead |
| T-079 | Retention purge test | 2 | Mid-Junior |
| T-030 | Schema activation no-redeployment test | 2 | Mid-Junior |
| T-031 | Schema Registry integration tests | 3 | Mid |
| T-037 | Pipeline crash recovery test: kill worker, restart, assert resume | 3 | Lead |
| T-081 | Alert rules: DLQ>50/5min, breaker OPEN, p95>30s, err>5% | 2 | Mid-Junior |
| T-082 | LLM latency + cost metrics: per-call histogram, token usage counter, breaker state gauge | 2 | Mid-Junior |
| T-083 | Structured log assertions: no PII in logs, tenant_id + document_id in all lines | 2 | Mid-Junior |
| T-084 | Observability integration test: /metrics counters verified after full pipeline run | 2 | Mid-Junior |

> Total test + config sweep: ~67 points across 27 tasks. This is distributed across the full team in Sprints 5 and 6, interleaved with feature tasks. Tasks with no upstream feature dependency (T-080, T-081, T-082, T-083, T-084, T-050, T-054) can start as soon as the features they test land in the sprint.

### Sprint 6 Acceptance Criteria
- [ ] GDPR erasure of in-flight document: pipeline halts within 1 node boundary, PII fields absent from PG + Qdrant, tombstone in audit_log
- [ ] Schema v2 activated while v1 doc is in-flight: v1 doc completes on v1 schema; new submission uses v2
- [ ] Seed upload: 3 seed docs uploaded → activation succeeds; 2 seed docs → activation blocked (422)
- [ ] Review accept: webhook fires with accepted fields; Qdrant gains a new few-shot vector for the schema
- [ ] Stale review (24h+) fires notification (logged at MVP)
- [ ] `/metrics` endpoint: ingestion counter incremented, pipeline latency histogram populated, DLQ counter visible
- [ ] All 51 Gherkin scenarios (SC-001–SC-051) pass in CI
- [ ] Security: RLS adversarial test suite (SP-004) fully applied to all 10 tenant-scoped tables; no cross-tenant data returned under any query pattern
- [ ] No PII fields appear in any structured log output

### Sprint 6 Risk Gate
| Open Issue | Must Resolve By | Owner |
|-----------|----------------|-------|
| I-001: LLM DPA signed (hard blocker for PII pilot go-live) | Start of Sprint 6 | PM/Legal |
| T-075/T-076 GDPR in-flight complexity (8+5 pts on Lead) | Sprint 6 Week 1 | Lead |

---

**Milestone M-3 (End of Sprint 6):** PILOT-READY — all 55 MUST requirements covered, all Gherkin scenarios pass, GDPR erasure functional, observability wired, schema registry live. Platform ready for first PII tenant onboarding (pending I-001 DPA resolution).

---

## Task Dependency Graph (Critical Path)

The primary critical path runs through 20 tasks spanning Sprints 1–4. Delay on any of these tasks delays the STP demo milestone.

```
T-001 (scaffold)
  └─ T-003 (SQLAlchemy engine)
       └─ T-006 (Alembic init)
            └─ T-009 (initial schema migration)
                 └─ T-010 (RLS policies)  ← SP-004 feeds here
                      └─ T-012 (ORM models)
                           └─ T-015 (JWT middleware)
                                └─ T-017 (tenant context)
                                     └─ T-018 (PII encryption)
                                          └─ T-021 (POST /extract)
                                               └─ T-023 (document record + enqueue)
                                                    └─ T-032 (ExtractionState)
                                                         └─ T-033 (LangGraph graph)  ← SP-001 feeds here
                                                              └─ T-034 (PG checkpoint)
                                                                   └─ T-035 (pipeline worker)
                                                                        └─ T-038 (LlamaParse)  ← SP-002 feeds here
                                                                             └─ T-040 (RAG retrieval)
                                                                                  └─ T-041 (LCEL extraction)
                                                                                       └─ T-051 (confidence scorer)
                                                                                            └─ T-052 (route node)
                                                                                                 └─ T-055 (webhook builder)
                                                                                                      └─ T-056 (webhook delivery)
                                                                                                           └─ [STP COMPLETE]
```

Secondary critical path (GDPR compliance gate):
```
T-033 (LangGraph graph)
  └─ T-036 (GDPR cancellation flag)  ← SP-003 feeds here
       └─ T-075 (erasure endpoint)
            └─ T-076 (erasure orchestrator)
                 └─ T-078 (erasure tests)
                      └─ [GDPR PILOT GATE CLEARED]
```

### Cross-Sprint Dependency Map

| Task | Sprint | Unblocks | Sprint |
|------|--------|---------|--------|
| T-001 | 1 | T-002, T-003, T-004, T-005, T-006, T-008, T-032 | 1–2 |
| T-009 | 1 | T-010, T-011, T-012 | 1–2 |
| T-010 | 1 | T-014 (RLS tests) | 2 |
| T-012 | 2 | T-013, T-015, T-016, T-071 | 2–5 |
| T-017 | 2 | T-019, T-021, T-026, T-064 | 3–4 |
| T-018 | 2 | T-042 (extraction persistence) | 4 |
| T-033 | 3 | T-034, T-035, T-036, T-059 | 3–5 |
| T-039 | 4 | T-040, T-044, T-028, T-065 | 4–6 |
| T-041 | 4 | T-042, T-051, T-055, T-062 | 4–5 |
| T-048 | 5 | T-051 (confidence scorer) | 5 |
| T-064 | 4 | T-065, T-066, T-067, T-069, T-070 | 6 |
| T-071 | 5 | T-073, T-074, T-077 | 6 |
| T-036 | 6 | T-075 | 6 |
| SP-001 | 2 | T-034 | 3 |
| SP-002 | 3 | T-038 | 4 |
| SP-003 | 5 | T-075, T-076 | 6 |
| SP-004 | 1 | T-010, T-014 | 1–2 |

### Parallelization Opportunities

| Sprint | Lead | Mid Backend | Mid-Junior/Infra |
|--------|------|-------------|-----------------|
| 1 | T-001, T-004, SP-004 | T-003, T-006, T-009, T-010 | T-002, T-005, T-007, T-008 |
| 2 | T-015, T-016, T-017, T-018, SP-001, T-032 | T-011, T-012, T-013 | T-014 |
| 3 | T-033, T-034 | T-019, T-021–T-024, T-026 | T-020, T-025, SP-002 support |
| 4 | T-035, T-041, T-051 | T-038, T-039, T-040, T-064 | T-052, T-055 |
| 5 | T-062, T-071, SP-003 | T-046, T-048, T-056, T-060 | T-045, T-047, T-057, T-059 |
| 6 | T-065, T-075, T-076, T-036, T-037, T-078 | T-027, T-028, T-029, T-042, T-070, T-072, T-077 | T-066–T-068, T-049–T-050, T-058, T-063, T-069, T-073–T-074, T-079–T-084 |

---

## Milestone Summary

| Milestone | Sprint | Description |
|-----------|--------|-------------|
| M-0: Dev Environment Live | End Sprint 1 | Docker Compose up, CI green, auth 401/202, RLS pass |
| M-1: STP Happy Path Demo | End Sprint 3 | Invoice PDF in → HMAC-signed webhook out within 15s p95; schema registry create + activate demo |
| M-2: Invoice-In / Webhook-Out Pilot Core | End Sprint 4 | Full routing (HIGH/MEDIUM/LOW), review queue, DLQ wired, circuit breaker wired |
| M-3: Feature Complete | End Sprint 5 | Guardrails, webhook hardening, audit service, GDPR at-rest, schema versioning + seeds |
| M-4: Pilot-Ready / MVP | End Sprint 6 | GDPR in-flight, all integration tests green, observability, pilot tenant onboardable (pending DPA I-001) |

---

## Definition of Done (Per-Task Checklist)

Every task in this sprint plan is DONE only when ALL of the following apply:

- [ ] Unit tests written and passing (pytest-asyncio); coverage >= 80% for new code in this task
- [ ] Integration test: happy path + at least one error/edge case covered
- [ ] If database change: Alembic migration written, `upgrade head` verified, `downgrade -1` verified
- [ ] If task touches a tenant-scoped table: cross-tenant isolation test included (no row from another tenant returned)
- [ ] PII handling: no PII fields appear in log output; AES-256-GCM encryption applied to pii_fields[] where required
- [ ] Audit event: every state-changing operation calls `audit_service.append_event()` with event_type, actor, payload_hash
- [ ] Prometheus metric updated: counter incremented or histogram observed for any observable operation
- [ ] Structured JSON log line emitted at entry/exit of every pipeline node (tenant_id + document_id present)
- [ ] No secrets or credentials in code; all config via pydantic-settings / environment variables
- [ ] Code review: approved by at least one other engineer before merge
- [ ] `ruff` lint and `mypy` type-check pass with zero new errors
- [ ] GDPR note: if task processes or stores PII fields, erasure path is identified and tracked in a comment

---

## Risks & Blockers

| Risk | Likelihood | Impact | Sprint | Mitigation |
|------|-----------|--------|--------|-----------|
| LangGraph checkpoint-postgres recovery semantics unclear (SP-001) | High | High | 2 | 2-day spike; fallback = restart-from-scratch with idempotent nodes |
| LlamaParse cloud latency violates 15s p95 SLA (I-003, SP-002) | Medium | High | 3 | SP-002 spike day 1; pdfplumber fallback contracted; negotiate dedicated LlamaParse plan |
| GDPR in-flight erasure partial failure leaves PII behind (SP-003) | Medium | Critical | 5–6 | SP-003 spike; compensating transaction design; accept at-rest only for pilot if unresolved |
| RLS misconfiguration cross-tenant data leak (SP-004) | Medium | Critical | 1 | SP-004 adversarial suite applied to T-010; security review before PII tenant onboarded |
| LLM provider DPA not signed (I-001) | High | High | All | Legal track runs parallel from Sprint 1; synthetic data only until signed |
| Invoice required fields unconfirmed (I-002) | Medium | High | 3 | PM confirms with pilot tenant by end of Sprint 3; gates T-051 confidence scorer |
| PII encryption key management not designed (DM-001) | Medium | High | 2 | Design key derivation scheme in T-018; document key rotation plan |
| asyncio circuit breaker state not shared across workers (D-009) | Low | Medium | 5 | Known limitation; single-process deployment for MVP mitigates; documented |
| Qdrant post-query assertion missing → cross-tenant vectors leaked | Low | Critical | 4 | T-039 mandatory assertion; T-044 cross-tenant test; CRITICAL log on omission |
| Schema versioning race condition on in-flight doc (REQ-025) | Low | Medium | 6 | Optimistic lock on schema.current_version; T-030 test covers scenario |

---

## Out of Scope

| Item | Deferred to |
|------|-----------|
| SSO / SAML integration | Phase 2 |
| Embedded PDF viewer in review UI | Phase 2 |
| Multi-modal vision extraction | Phase 2 |
| Data residency / geo-fencing | Phase 2 |
| ERP connectors (SAP, Oracle) | Phase 2 |
| Cross-tenant schema sharing | Phase 2 |
| Reviewer assignment routing | Phase 2 |
| Bulk-accept in review queue | Phase 2 |
| OpenTelemetry distributed tracing | Phase 2 |
| Auto prompt generation from schema | Phase 2 |
| Duplicate document detection | Phase 2 |
| S3 file storage (production) | Phase 2 (T-022 uses local fs adapter at MVP) |
| Self-hosted LlamaParse | Phase 2 (I-003 resolved as cloud for MVP) |
| vLLM on-premise LLM stack | Phase 2 (I-004, conditional on on-premise requirement) |
| Production Kubernetes hardening (HPA tuning, load tests) | Phase 2 (T-007 is skeleton only) |
| `{PIPELINE_DOCS}/09-implementation-log.md` updated | Updated by @java-developer and @angular-frontend-engineer agents |
