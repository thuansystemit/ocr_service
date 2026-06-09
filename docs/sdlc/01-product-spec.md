# Product Spec — Enterprise OCR / Document Extraction Platform
**Date:** 2026-06-09
**Author:** @product-manager
**Status:** DRAFT
**Feature ID:** enterprise-ocr-platform

---

## Problem Statement
Enterprises processing high document volumes today build fragmented, single-use extractors (see: `cv-batch-extractor`) with no shared schema registry, no multi-tenant isolation, and no human-in-the-loop review lane. Each team reinvents the same guardrail, prompt, and dead-letter logic. This platform replaces every bespoke extractor with a single, multi-tenant, extensible OCR and document-extraction service — built on LangChain, LangGraph, LlamaParse, and a vector DB — that any business unit or enterprise customer can operate without writing extraction code. New document types ship in under one business day (schema + prompt + few-shot examples), not weeks.

---

## Target Users
| Persona | Key need | Estimated reach (users/quarter) |
|---------|----------|---------------------------------|
| Ops Analyst | Accurate structured output, zero manual re-keying | 500–2,000 per tenant |
| Document Engineer | Low-code tooling to onboard new doc types; fast prompt iteration | 5–20 per tenant |
| Tenant Admin | Tenant isolation, API keys, audit logs, SLA monitoring | 2–5 per tenant |
| Platform Operator | Observability, scaling, cost management, model upgrades | 3–8 internal |
| Compliance Officer | Immutable audit trail, PII handling evidence, retention policies | 1–3 per tenant |

---

## User Stories

### US-001: Invoice Extraction — Straight-Through Processing
As an Ops Analyst, I want to submit an invoice PDF via API and receive a structured JSON of all invoice fields automatically, so that I eliminate manual data entry and feed downstream ERP systems with zero re-keying.

**Acceptance Criteria:**
- [ ] Given a valid PDF invoice under 50 MB, when I POST to `/api/v1/extract` with `document_type=invoice` and a valid tenant API key, then I receive HTTP 202 with a `document_id` within 500 ms
- [ ] Given a standard 2-page machine-readable invoice PDF, when the pipeline completes (STP path), then the webhook fires within 15 seconds (p95)
- [ ] Given a HIGH-confidence extraction result, when the pipeline routes it, then the result is delivered via webhook with no human intervention required
- [ ] Given an extracted invoice result, then it contains `invoiceNumber`, `invoiceDate`, `vendorName`, `totalAmount`, `currency` (required fields); any missing required field drives `confidence: LOW` and routes to the review queue
- [ ] Given any extraction outcome (PASS / DEGRADED / REJECTED / ERROR), then the tenant's configured webhook always receives a callback — the platform never silently drops documents
- [ ] Given an unsupported file type (e.g. `.exe`), when submitted, then the API returns HTTP 422 with error code `UNSUPPORTED_FILE_TYPE`

**Out of scope for this story:** ERP push/sync integration; duplicate invoice detection (US-004); multi-page invoice > 50 pages
**RICE Score:** Reach=1500 × Impact=3 × Confidence=90% / Effort=4 = **1013**

---

### US-002: Human-in-the-Loop Review
As an Ops Analyst, I want to see a review queue of MEDIUM-confidence documents with extracted fields editable inline, so that I can correct and approve uncertain extractions without leaving the platform.

**Acceptance Criteria:**
- [ ] Given a document with `confidence: MEDIUM`, when the pipeline completes, then the document appears in the review queue within 60 seconds
- [ ] Given a review queue item, when I open it, then I see extracted JSON fields in an editable form alongside a link to the original document
- [ ] Given a corrected field, when I click Accept, then the correction is saved, the updated result fires via webhook, and the corrected record is written to the vector DB as a new few-shot example
- [ ] Given each review action (accept / correct / reject), then it is recorded in the audit log with `reviewer_id` and `timestamp`
- [ ] Given a review item older than 24 hours, then the Tenant Admin receives a notification (email or Slack, configurable)

**Out of scope for this story:** Embedded PDF viewer (Phase 2); bulk-accept of multiple documents; reviewer assignment routing
**RICE Score:** Reach=800 × Impact=2 × Confidence=85% / Effort=3 = **453**

---

### US-003: Self-Service New Document Type Onboarding
As a Document Engineer, I want to register a new extraction schema and upload seed examples via API, so that I can onboard a new document type in under one business day without platform team involvement.

**Acceptance Criteria:**
- [ ] Given a JSON Schema definition, when I POST to `/api/v1/schemas`, then a new schema is created with `status: draft` and a generated LangChain prompt template within 5 seconds
- [ ] Given a draft schema, when I upload at least 3 labelled seed documents via `/api/v1/schemas/{id}/examples`, then they are indexed in the tenant's Qdrant collection
- [ ] Given a draft schema with seeds, when I call `/api/v1/extract?dry_run=true`, then the platform returns extracted JSON + confidence scores without persisting results or triggering webhooks
- [ ] Given a schema in `status: draft`, when I PATCH it to `status: active`, then it is available for live extraction with no platform redeployment
- [ ] Given an active schema version, when I publish a new version, then the old version remains available and in-flight documents complete on the version they started

**Out of scope for this story:** Schema UI (admin API only at MVP); automated prompt generation from examples; cross-tenant schema sharing
**RICE Score:** Reach=60 × Impact=3 × Confidence=80% / Effort=3 = **48**

---

### US-004: Multi-Tenant Isolation & API Key Management
As a Tenant Admin, I want all my documents, schemas, extracted results, audit logs, and vector DB examples to be fully isolated from other tenants, so that there is zero risk of data leakage.

**Acceptance Criteria:**
- [ ] Given any API request, when the JWT does not include a valid `tenant_id` claim, then the platform returns HTTP 401
- [ ] Given a valid JWT for Tenant A, when I query any document, schema, or audit endpoint, then results are restricted to Tenant A's data only — enforced by PostgreSQL row-level security at the DB layer, not just application code
- [ ] Given a vector DB query at extraction time, when the query executes, then the Qdrant filter always includes `tenant_id`; a query missing this filter is rejected at the service layer
- [ ] Given PII fields declared in a schema's `pii_fields[]`, then those values are AES-256 encrypted at rest and replaced with `[REDACTED]` in all log output
- [ ] Given a Tenant Admin, when they POST to `/api/v1/admin/api-keys`, then a new scoped API key is created with optional `description` and optional `expires_at`; revoked keys return HTTP 401 within 100 ms

**Out of scope for this story:** SSO/SAML (Phase 3); role-based access within a tenant (Phase 2)
**RICE Score:** Reach=2000 × Impact=3 × Confidence=95% / Effort=4 = **1425**

---

### US-005: Audit Trail & Compliance Export
As a Compliance Officer, I want a complete, immutable, per-document audit trail that I can export on demand, so that I can demonstrate data handling compliance to auditors.

**Acceptance Criteria:**
- [ ] Given any pipeline event (ingest / guard / LLM call / delivery / review), then an audit record is appended with `tenant_id`, `document_id`, `event_type`, `actor`, `timestamp`, `status`, and SHA-256 hash of any payload
- [ ] Given the audit table, then no UPDATE or DELETE is permitted — enforced by a PostgreSQL trigger; any attempt returns an error
- [ ] Given a Compliance Officer request, when I call `GET /api/v1/audit?from=&to=`, then the tenant's full audit log is returned as NDJSON or CSV within 30 seconds for up to 90 days of history
- [ ] Given a GDPR erasure request, when I call `DELETE /api/v1/documents/{id}`, then document content and PII fields are hard-deleted; a tombstone record remains in the audit log (no content, just event metadata)

**Out of scope for this story:** Cross-tenant audit aggregation; real-time audit streaming
**RICE Score:** Reach=300 × Impact=2 × Confidence=90% / Effort=2 = **270**

---

### US-006: Dead-Letter Queue & Observability
As a Platform Operator, I want Prometheus metrics, structured logs, and a dead-letter queue management API, so that I can detect and recover from pipeline failures before they breach tenant SLAs.

**Acceptance Criteria:**
- [ ] Given the platform is running, when I scrape `/metrics`, then I receive `ocr_documents_ingested_total`, `ocr_documents_completed_total`, `ocr_documents_rejected_total`, `ocr_extraction_duration_seconds` (histogram), `ocr_llm_tokens_used_total`, `ocr_review_queue_depth`
- [ ] Given a document that reaches REJECTED or ERROR status, then it is written to the DLQ with `document_id`, `tenant_id`, `failure_reason`, `pipeline_state`, `timestamp`
- [ ] Given the DLQ, when I call `GET /api/v1/admin/dlq`, then I receive a paginated list filterable by tenant and status
- [ ] Given a DLQ item, when I call `POST /api/v1/admin/dlq/{id}/retry`, then the document re-enters the pipeline from the start
- [ ] Given the LLM circuit breaker opening (5 failures in 60 s), then an alert fires within 2 minutes via the configured alerting channel

**Out of scope for this story:** Grafana dashboard templates (separate deliverable); OpenTelemetry tracing (Phase 2)
**RICE Score:** Reach=10 × Impact=2 × Confidence=90% / Effort=2 = **9** *(internal infra — non-negotiable regardless of score)*

---

## Prioritized Backlog
| # | Story ID | Title | RICE Score | Priority | Target Sprint |
|---|----------|-------|-----------|---------|--------------|
| 1 | US-004 | Multi-Tenant Isolation & API Key Management | 1425 | P0 | Sprint 1 |
| 2 | US-001 | Invoice Extraction — STP path | 1013 | P0 | Sprint 1–2 |
| 3 | US-002 | Human-in-the-Loop Review | 453 | P1 | Sprint 2–3 |
| 4 | US-005 | Audit Trail & Compliance Export | 270 | P1 | Sprint 3 |
| 5 | US-006 | Dead-Letter Queue & Observability | 9* | P0 | Sprint 1 (infra) |
| 6 | US-003 | Self-Service New Document Type Onboarding | 48 | P2 | Sprint 4–5 |

---

## MVP Scope

**MUST ship (Sprint 1–4):**
- US-004 Multi-tenant isolation (foundational; blocks everything else)
- US-001 Invoice extraction end-to-end (REST ingest → LlamaParse → LangGraph → LangChain + Qdrant RAG → guardrails → webhook)
- US-002 Human review queue (minimal: list + field editor, no embedded PDF viewer)
- US-005 Audit log (append-only, export endpoint)
- US-006 Dead-letter queue + Prometheus metrics

**SHOULD ship (Sprint 5–6):**
- US-003 Self-service schema onboarding (admin API)
- Deduplication via hash + vector similarity
- Batch submission endpoint

**WILL NOT ship (this release):**
- SSO/SAML integration — reason: API key auth sufficient for pilot; SSO needed for Series A enterprise deals
- Embedded PDF viewer in review UI — reason: link to source file sufficient at MVP
- Multi-modal vision path — reason: LlamaParse covers 90%+ of invoice formats; vision path adds cost and complexity
- Data residency controls (per-tenant region/provider) — reason: single-region deployment at MVP
- Cost optimization / model routing — reason: validate accuracy first, then optimize cost in Phase 3
- ERP/SAP/QuickBooks push connectors — reason: webhook covers all downstream integrations; connectors are customer-specific

---

## Success Metrics
| Metric | Current baseline | Target | How measured |
|--------|-----------------|--------|-------------|
| Extraction accuracy (field-level F1) | N/A | >= 90% on invoice fields | Monthly labeled eval set, 200 docs per schema |
| Straight-through processing (STP) rate | N/A | >= 75% HIGH confidence, no review needed | `PASS docs / total docs` via Prometheus |
| End-to-end latency p95 | N/A | < 15 s for 2-page PDF (STP path) | `ocr_extraction_duration_seconds` histogram |
| Cost per document | N/A | < $0.05 (LLM tokens + infra) | Monthly LLM cost / docs processed |
| Human review rate | N/A | <= 20% of docs require review | `MEDIUM confidence docs / total docs` |
| Time to onboard new doc type | Days–weeks (bespoke build) | < 1 business day with 10 seed examples | Measured during onboarding sessions |
| Dead-letter rate | N/A | < 2% of all documents | `DLQ docs / total docs` |
| Tenant SLA: review queue age | N/A | No item older than 24 h without notification | Alert rule on review queue depth |

---

## Non-Functional & Enterprise Requirements

### Multi-Tenancy & Isolation
- All database tables with tenant data MUST have a `tenant_id` column. PostgreSQL RLS enforced at DB layer.
- Vector DB namespaces MUST be per-tenant. No cross-tenant query possible at the Qdrant service layer.
- LLM prompt context MUST never include examples or results from a different tenant.

### Security
- All API traffic over TLS 1.2+. JWT Bearer (RS256) for authentication.
- PII fields declared in schema's `pii_fields[]` encrypted at rest (AES-256) and masked in all logs.
- Prompt injection detection on all ingested text before it reaches the LLM.
- Webhook payloads signed with HMAC-SHA256; consumers must verify before processing.

### Auditability & Compliance
- Audit log: append-only, PostgreSQL trigger prevents UPDATE/DELETE.
- Every extraction event traceable end-to-end: `document_id → parse_result → guardrail_reports[] → llm_request_id → extracted_json_hash → delivery_event → review_event`.
- Configurable document retention per tenant (default 90 days). Nightly purge job; purge events logged.
- GDPR erasure: hard-delete content + PII; tombstone audit record retained.

### Confidence Scoring
- Every result carries `confidenceOverall` (HIGH/MEDIUM/LOW) + `lowConfidenceFields[]`.
- Confidence = min(LLM self-report, schema completeness score, semantic validation score).
- Thresholds (default): HIGH >= 0.85, MEDIUM 0.60–0.84, LOW < 0.60. Configurable per schema.
- Confidence thresholds and routing decision stored in audit log.

### Scalability & Performance
- Target throughput: 100 docs/min per tenant; 1,000 docs/min platform-wide.
- p95 end-to-end latency for 2-page PDF: < 15 s (STP path).
- Async worker pool, configurable concurrency per tenant (default 10). LangGraph state persisted to PostgreSQL.
- If per-tenant queue exceeds `max_queue_size` (default 500): return HTTP 429 with `Retry-After`.

### Observability
- Structured JSON logs on every pipeline step (tenant_id, document_id, event, duration_ms, model_used, token_usage).
- Prometheus metrics at `/metrics`. OpenTelemetry distributed tracing (Phase 2).
- Default alerts: DLQ depth > 50 for 5 min; circuit breaker OPEN; p95 latency > 30 s; error rate > 5%.

---

## Technology Recommendations

| Concern | Recommended choice | Rationale |
|---------|-------------------|-----------|
| API framework | FastAPI + Uvicorn | Async, native Pydantic, auto-OpenAPI |
| LLM orchestration | LangChain (LCEL) | Provider-agnostic; native LangGraph integration |
| Workflow engine | LangGraph | Stateful DAG with checkpointing; purpose-built for multi-step LLM pipelines |
| PDF/image parsing | LlamaParse cloud API | Best structured output from complex PDFs, tables, scanned docs |
| Vector DB | Qdrant | Multi-tenant collections, fast ANN, simple Docker deploy |
| Primary LLM | Anthropic Claude claude-sonnet-4-6 | Strong structured extraction, JSON mode |
| Fallback LLM | OpenAI GPT-4o | Coverage if Anthropic unavailable |
| Relational DB | PostgreSQL 16 | Audit log, schema registry, LangGraph state, RLS |
| Workflow state | langgraph-checkpoint-postgres | Single DB; no Redis dependency at MVP |
| Schema validation | Pydantic v2 | Fast, battle-tested, used in prior art |
| Containerization | Docker Compose (dev) → Kubernetes (prod) | Simple local dev; K8s for production scaling |
| Observability | Prometheus + Grafana + OpenTelemetry | Standard enterprise stack; no vendor lock-in |

---

## Open Questions
| # | Question | Recommended default | Owner | Due |
|---|----------|-------------------|-------|-----|
| 1 | LlamaParse cloud API vs self-hosted? | Cloud API at MVP; evaluate self-hosted in Phase 2 for data residency | Platform Operator | Sprint 1 kickoff |
| 2 | Vector DB: Qdrant vs Weaviate vs pgvector? | Qdrant (best multi-tenancy + perf/simplicity ratio at this scale) | Platform Operator | Sprint 1 kickoff |
| 3 | LLM provider DPAs signed before production? | Required blocker before pilot launch if any tenant processes PII | Compliance Officer | Before pilot launch |
| 4 | On-premise deployment required by any pilot tenant? | Flag immediately — changes LLM stack to self-hosted vLLM; significant infra cost | Tenant Admin | Sprint 1 |
| 5 | Invoice schema required vs optional fields? | Required: invoiceNumber, invoiceDate, vendorName, totalAmount, currency | Document Engineer | Sprint 1 |
| 6 | LangGraph state: PostgreSQL vs Redis? | PostgreSQL via langgraph-checkpoint-postgres; no Redis at MVP | Platform Operator | Sprint 1 |
| 7 | Correction-to-few-shot: immediate write or gated? | Immediate at MVP; gate on Document Engineer approval in Phase 2 | Product | Sprint 3 planning |
