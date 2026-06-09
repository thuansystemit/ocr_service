# Product Spec — Enterprise OCR / Document Extraction Platform
**Date:** 2026-06-09
**Author:** @product-manager
**Status:** DRAFT
**Feature ID:** enterprise-ocr-platform

---

## 1. Product Vision & Problem Statement

### Vision
A single, multi-tenant extraction platform that any business unit or customer can point at any document type — invoices, contracts, receipts, onboarding forms, purchase orders — and receive clean, validated, structured JSON within seconds, with full auditability and a human-in-the-loop review lane for low-confidence results.

### Problem Statement
Enterprises processing high document volumes today face three compounding problems:

1. **Fragmented tooling.** Each team builds its own one-off extractor (see: `cv-batch-extractor`). Logic, prompts, guardrails, and schemas diverge. There is no shared corpus of extraction examples, no shared confidence scoring, and no shared dead-letter/review queue.
2. **No multi-tenant isolation.** A single extractor built for one business unit cannot safely serve another without data leakage risk and cross-contamination of prompts, schemas, and audit logs.
3. **Brittle LLM pipelines.** Direct LLM calls without stateful workflow management fail unpredictably on complex multi-page documents. There is no retry intelligence, no partial-result recovery, and no human escalation path baked in.

**Target outcome:** Replace every bespoke extractor with one platform. New document types ship in days (schema + prompt + few-shot examples), not months.

---

## 2. Target Users & Personas

| Persona | Role | Key need | Estimated reach (users/quarter) |
|---------|------|----------|---------------------------------|
| **Ops Analyst** | End-user of extracted data | Accurate structured output, zero manual re-keying | 500–2,000 per tenant |
| **Document Engineer** | Defines schemas, prompts, few-shot examples for a doc type | Low-code tooling to onboard new doc types; fast iteration on prompts | 5–20 per tenant |
| **Tenant Admin** | IT/platform owner at each enterprise customer | Tenant isolation, API keys, audit logs, SLA monitoring | 2–5 per tenant |
| **Platform Operator** | Internal SRE/DevOps at the OCR vendor | Observability, scaling, cost management, model upgrades | 3–8 internal |
| **Compliance Officer** | Risk/legal at each enterprise customer | Immutable audit trail, PII handling evidence, retention policies | 1–3 per tenant |

---

## 3. Core Use Cases & User Journeys

### UC-001 — Invoice Extraction (Primary MVP Use Case)

**Actor:** Ops Analyst / upstream ERP system (automated)

**Happy path:**
1. Client uploads a PDF invoice via REST API (or drops file on a watched S3/GCS/SFTP path).
2. Platform assigns a `document_id`, records `tenant_id`, timestamps ingestion.
3. LlamaParse converts the PDF to structured markdown/text (handles scanned PDFs with OCR fallback).
4. Input guardrails run: file size, MIME type, text length, text quality, injection detection.
5. LangGraph extraction workflow activates the `invoice` schema node: LangChain calls the configured LLM with tenant-scoped prompt + RAG-retrieved few-shot examples from the vector DB.
6. Output guardrails run: JSON parse, schema validation (Pydantic), semantic checks (date coherence, currency codes, line-item math), confidence scoring.
7. If confidence is HIGH: result is auto-delivered via webhook / API response. Straight-through processing (STP).
8. If confidence is MEDIUM: result is flagged; human review task is created in the review UI. Analyst confirms or corrects fields. Corrected record is written back to the vector DB as a new few-shot example.
9. If confidence is LOW or BLOCK: document goes to dead-letter queue with full audit context; Ops Analyst is notified.

**Key extracted fields (invoice schema v1):**
- `invoiceNumber`, `invoiceDate`, `dueDate`
- `vendorName`, `vendorAddress`, `vendorTaxId`
- `buyerName`, `buyerAddress`, `buyerTaxId`
- `lineItems[]`: `{ description, quantity, unitPrice, totalPrice, taxRate }`
- `subtotal`, `taxAmount`, `totalAmount`, `currency`
- `paymentTerms`, `purchaseOrderNumber`, `bankDetails`
- `confidenceOverall`, `lowConfidenceFields`, `missingFields`

---

### UC-002 — General Document Extraction

**Actor:** Document Engineer (setup) + Ops Analyst (runtime)

**Happy path:**
1. Document Engineer defines a new extraction schema via the Schema Registry UI/API: field names, types, required/optional, validation rules.
2. Engineer uploads 5–20 labelled example documents as few-shot seeds into the vector DB.
3. Optionally writes a custom extraction prompt or uses the platform default with schema injection.
4. Ops Analyst (or automated pipeline) submits documents; platform routes to the correct schema via `document_type` parameter on the API.
5. Extraction, guardrails, confidence, and delivery follow the same pipeline as UC-001.

---

### UC-003 — Onboarding a New Document Type

**Actor:** Document Engineer

**Happy path:**
1. Engineer calls `POST /api/v1/schemas` with a JSON Schema + display name + extraction hints.
2. Platform generates a base LangChain prompt template (with schema injected) and stores it in the Prompt Registry.
3. Engineer uploads labelled seed documents (minimum 3 recommended) to the vector DB via `POST /api/v1/schemas/{schema_id}/examples`.
4. Engineer calls `POST /api/v1/extract?dry_run=true` with a sample document; platform returns extracted JSON + confidence scores without writing results.
5. Engineer iterates on schema/prompt until confidence is acceptable (target: >= 85% HIGH confidence on seeds).
6. Engineer publishes the schema (`PATCH /api/v1/schemas/{schema_id}` with `status: active`).
7. New doc type is live for the tenant. No platform-level deployment required.

---

## 4. Key Features & Capabilities

### 4.1 MVP Features (Phase 1)

| # | Feature | Technology | Description |
|---|---------|-----------|-------------|
| F-01 | **Ingestion API** | FastAPI | REST endpoint for single-doc and batch upload; S3/GCS polling watcher as alternative ingestion path |
| F-02 | **Document Parsing** | LlamaParse | PDF (native + scanned), DOCX, PNG/JPEG → structured markdown/text. Handles multi-page, tables, multi-column layouts |
| F-03 | **Extraction Workflow** | LangGraph | Stateful DAG per document type: parse → guard → extract → validate → route. Each node is independently retryable. State persisted to allow resume after failure |
| F-04 | **LLM Extraction** | LangChain | Schema-aware prompt templates per doc type; supports Claude, GPT-4o, Gemini as interchangeable backends via LangChain abstraction. Default: Claude claude-sonnet-4-6 |
| F-05 | **RAG Few-Shot Examples** | Vector DB (Qdrant — recommended default) | At extraction time, retrieve the top-K most similar labelled examples from the tenant's corpus; inject into LLM prompt. Improves accuracy without fine-tuning |
| F-06 | **Guardrail Pipeline** | Pydantic + custom guards | Input: file size, MIME, text length, text quality, injection. Output: JSON parse, schema validation, semantic checks, confidence scoring, sanitization. Inherit and extend from `cv-batch-extractor` pattern |
| F-07 | **Confidence Scoring** | LLM self-report + heuristic | LLM reports `confidenceOverall` (HIGH/MEDIUM/LOW) + `lowConfidenceFields[]`. Heuristic layer cross-checks with schema completeness. Combined score drives STP vs. human review routing |
| F-08 | **Human-in-the-Loop Review UI** | FastAPI + minimal React frontend | Review queue showing MEDIUM-confidence docs. Analyst sees original doc (PDF viewer) side-by-side with extracted JSON. Can accept, correct fields, or reject. Corrections fed back to vector DB |
| F-09 | **Schema Registry** | FastAPI + PostgreSQL | CRUD for extraction schemas per tenant. Versioned. Schemas stored as JSON Schema + Pydantic model generated at runtime |
| F-10 | **Webhook / Callback Delivery** | httpx async | On completion (STP or post-review), POST structured JSON to tenant-configured webhook URL. Retry with exponential backoff (3 attempts). Dead-letter on failure |
| F-11 | **Multi-Tenancy** | Middleware + DB row-level security | Every API call carries `tenant_id` (from JWT). All data (documents, results, schemas, examples, audit logs) is row-level isolated. No cross-tenant queries possible |
| F-12 | **Audit Log** | Append-only PostgreSQL table | Every pipeline event (ingestion, guard result, extraction attempt, delivery, correction) is recorded with `tenant_id`, `document_id`, `actor`, `timestamp`, `payload_hash` |
| F-13 | **Dead-Letter Queue** | NDJSON file + admin API | Documents that BLOCK or ERROR are written to DLQ with full context. Admin API to inspect, retry, or discard |

### 4.2 Phase 2 Features (Post-MVP)

| # | Feature | Notes |
|---|---------|-------|
| F-14 | **Deduplication** | Hash-based + semantic similarity check against vector DB before extraction. Skip re-processing identical docs |
| F-15 | **Batch API** | `POST /api/v1/extract/batch` accepting ZIP or manifest of URLs. Async job tracking |
| F-16 | **Active Learning Loop** | Auto-identify low-confidence corrections made by analysts; flag as high-value training examples; alert Document Engineer to review and promote |
| F-17 | **Multi-modal extraction** | For image-heavy documents (e.g. receipts), use vision-capable LLM path (GPT-4o Vision / Claude claude-sonnet-4-6) directly on image, bypassing LlamaParse text extraction |
| F-18 | **Prompt A/B Testing** | Run two prompt variants on the same document; pick winner by confidence score; track per-schema over time |
| F-19 | **Cost Optimization Layer** | Route simple, short documents to cheaper/faster models (e.g. Haiku, GPT-4o-mini); reserve large models for complex/degraded docs |
| F-20 | **SSO / SAML / OIDC** | Enterprise identity integration per tenant |
| F-21 | **Data Residency Controls** | Tenant-level config for which LLM provider and which cloud region to use (EU data residency compliance) |

---

## 5. High-Level Functional Requirements

### 5.1 Ingestion

- **FR-ING-01:** Platform MUST accept documents via `POST /api/v1/extract` with `multipart/form-data` (file + metadata).
- **FR-ING-02:** Platform MUST support async ingestion: return `202 Accepted` + `document_id`; client polls `GET /api/v1/documents/{id}` or receives webhook.
- **FR-ING-03:** Platform MUST support a file-watcher mode for S3/GCS bucket polling as an alternative to REST push (configurable per tenant).
- **FR-ING-04:** Supported file types at MVP: PDF (native and scanned), DOCX, PNG, JPEG. Max file size: 50 MB (configurable per tenant, default 20 MB).
- **FR-ING-05:** Every ingested document MUST be assigned a globally unique `document_id` (UUID v7) and stored with `tenant_id`, `document_type`, `source_filename`, `ingested_at`, `checksum_sha256`.

### 5.2 Parsing

- **FR-PRS-01:** LlamaParse MUST be used as the primary parser for PDF and image inputs. Output: structured markdown preserving tables and layout.
- **FR-PRS-02:** If LlamaParse fails (API error, timeout), the pipeline MUST fall back to `pdfplumber` + `pytesseract` and mark the result as `parse_method: fallback`. Document proceeds with WARN status.
- **FR-PRS-03:** Parsed text MUST be stored against `document_id` for audit and retry purposes.

### 5.3 Extraction

- **FR-EXT-01:** Extraction MUST be driven by a LangGraph stateful workflow. The workflow graph is: `ingest → parse → input_guards → extract → output_guards → route`.
- **FR-EXT-02:** The extract node MUST use LangChain to call the configured LLM. The prompt MUST include: (a) system instructions, (b) the target JSON schema, (c) top-3 RAG-retrieved few-shot examples from the tenant's vector DB, (d) the parsed document text.
- **FR-EXT-03:** The platform MUST support at least two interchangeable LLM backends: Anthropic Claude and OpenAI GPT-4o. LLM selection is a per-tenant config.
- **FR-EXT-04:** The extraction step MUST implement a circuit breaker: open after 5 consecutive LLM failures within a 60-second window; cool-down 120 seconds. Documents that arrive while the circuit is open go to the DLQ immediately.
- **FR-EXT-05:** Failed extractions MUST be retried up to 2 times before being sent to DLQ.

### 5.4 Validation & Guardrails

- **FR-VAL-01:** Input guardrails (run before LLM): file size check, MIME type check, text length check (BLOCK if 0 chars; WARN + truncate at 100k chars), text quality check (WARN if < 20 words or < 80% printable), prompt injection check (WARN + sanitize if LLM-override patterns found).
- **FR-VAL-02:** Output guardrails (run after LLM): JSON parse check (BLOCK on failure), Pydantic schema validation (BLOCK on hard violations, WARN on soft/optional fields missing), semantic validation (WARN on invalid dates, mismatched currency codes, line-item math errors), confidence scoring, output sanitization (strip control chars, cap field lengths).
- **FR-VAL-03:** Processing status hierarchy: `PASS → DEGRADED → REJECTED → ERROR`. The backend/webhook always receives a callback regardless of status. The platform never silently drops documents.
- **FR-VAL-04:** Each guardrail MUST produce a `GuardrailReport` (guard name, status, reason, metadata). All reports MUST be attached to the audit log entry.

### 5.5 Human-in-the-Loop Review

- **FR-HIL-01:** Documents with `confidence: MEDIUM` MUST be routed to the human review queue automatically.
- **FR-HIL-02:** The review UI MUST show the original document (PDF/image embed) and the extracted JSON side-by-side. Analysts can edit field values inline.
- **FR-HIL-03:** Analyst corrections MUST be written back to the vector DB as a new labelled few-shot example (after a Document Engineer approval step in Phase 2; direct write in MVP).
- **FR-HIL-04:** Each review action (accept, correct, reject) MUST be logged in the audit trail with `reviewer_id` and `timestamp`.
- **FR-HIL-05:** SLA: review queue items older than 24h MUST trigger an email/Slack notification to the Tenant Admin.

### 5.6 Output & Integration

- **FR-OUT-01:** On document completion, the platform MUST POST the structured result to the tenant's configured webhook URL. Payload: `{ document_id, tenant_id, document_type, status, extracted_data, confidence, guardrail_warnings, processing_time_ms, reviewed_by }`.
- **FR-OUT-02:** Webhook delivery MUST retry 3 times with exponential backoff (2s, 8s, 32s). On final failure, write to DLQ and alert Tenant Admin.
- **FR-OUT-03:** The REST API MUST allow synchronous polling: `GET /api/v1/documents/{id}` returns current status and result when complete.
- **FR-OUT-04:** Platform MUST provide a bulk export endpoint: `GET /api/v1/documents?tenant_id=X&from=&to=&status=` returning NDJSON or CSV.

---

## 6. Non-Functional & Enterprise Requirements

### 6.1 Multi-Tenancy & Isolation

- **NFR-MT-01:** Every database table that stores tenant data MUST have a `tenant_id` column. Row-level security (PostgreSQL RLS) enforced at the DB layer — not just the application layer.
- **NFR-MT-02:** Tenant API keys MUST be hashed (bcrypt) before storage. Keys are never logged.
- **NFR-MT-03:** Vector DB namespaces MUST be per-tenant. No cross-tenant vector lookup is possible at the query level.
- **NFR-MT-04:** LLM prompt context MUST never include examples or prior results from a different tenant. Enforced by scoping all vector DB queries to `tenant_id` filter.

### 6.2 Security

- **NFR-SEC-01:** All API traffic over TLS 1.2+. Internal service mesh traffic also encrypted.
- **NFR-SEC-02:** Authentication: JWT Bearer tokens (RS256). Tenant Admins issue sub-tokens with configurable scope and expiry.
- **NFR-SEC-03:** PII fields (as declared in the schema's `pii_fields[]` list) MUST be encrypted at rest using AES-256 and masked in logs.
- **NFR-SEC-04:** Prompt injection detection MUST be active on all ingested text before it reaches the LLM (from FR-VAL-01).
- **NFR-SEC-05:** No document content or PII is ever sent to a third-party LLM provider unless that tenant has explicitly configured and consented to that provider.

### 6.3 Auditability & Compliance

- **NFR-AUD-01:** Audit log entries are append-only. No UPDATE or DELETE on the audit table. Enforce via PostgreSQL trigger.
- **NFR-AUD-02:** Every extraction event MUST be traceable end-to-end: `document_id → parse_result → guardrail_reports[] → llm_request_id → extracted_json_hash → delivery_event → (optional) review_event`.
- **NFR-AUD-03:** Audit logs MUST be exportable per tenant on demand.
- **NFR-AUD-04:** Document retention policy: configurable per tenant (default 90 days). Purge job runs nightly; purge events are themselves logged.
- **NFR-AUD-05:** GDPR right-to-erasure: `DELETE /api/v1/documents/{id}` hard-deletes document content and PII fields but retains a tombstone record in the audit log (no content, just the event).

### 6.4 Confidence Scoring

- **NFR-CON-01:** Every extraction result MUST carry `confidenceOverall` (HIGH / MEDIUM / LOW) and `lowConfidenceFields[]`.
- **NFR-CON-02:** Confidence is computed as the minimum of: (a) LLM self-reported confidence, (b) schema completeness score (required fields present / total required fields), (c) semantic validation score.
- **NFR-CON-03:** Confidence thresholds (default: HIGH >= 0.85, MEDIUM 0.60–0.84, LOW < 0.60) MUST be configurable per schema.
- **NFR-CON-04:** Confidence scores and the routing decision they drove MUST be stored in the audit log.

### 6.5 Scalability & Performance

- **NFR-PER-01:** Target throughput: 100 documents/minute per tenant at peak. Platform-wide: 1,000 documents/minute across all tenants on recommended hardware.
- **NFR-PER-02:** p95 end-to-end latency (ingest to webhook delivery) for a 2-page PDF: < 15 seconds (STP path).
- **NFR-PER-03:** Async worker pool with configurable concurrency per tenant (default: 10 workers). LangGraph workflow state persisted to PostgreSQL (or Redis) for crash recovery.
- **NFR-PER-04:** Backpressure: if the per-tenant queue exceeds `max_queue_size` (default 500), new submissions return `429 Too Many Requests` with `Retry-After` header.

### 6.6 Observability

- **NFR-OBS-01:** Structured JSON logs for every pipeline event (ingestion, each guardrail, LLM call start/end, delivery, review). Log fields: `tenant_id`, `document_id`, `event`, `duration_ms`, `status`, `model_used`, `token_usage`.
- **NFR-OBS-02:** Prometheus metrics exposed at `/metrics`: `ocr_documents_ingested_total`, `ocr_documents_completed_total`, `ocr_documents_rejected_total`, `ocr_extraction_duration_seconds` (histogram), `ocr_llm_tokens_used_total`, `ocr_review_queue_depth`.
- **NFR-OBS-03:** Distributed tracing with OpenTelemetry. Each document gets a `trace_id`. LangGraph node spans are instrumented.
- **NFR-OBS-04:** Alert rules (default, Grafana/Alertmanager): DLQ depth > 50 for 5 minutes; LLM circuit breaker OPEN; p95 latency > 30s; error rate > 5%.

---

## 7. Success Metrics / KPIs

| Metric | Current baseline | Phase 1 target | Phase 2 target | How measured |
|--------|-----------------|---------------|---------------|-------------|
| **Extraction accuracy (field-level F1)** | N/A (new platform) | >= 90% on invoice fields | >= 93% | Monthly labeled eval set, 200 docs per schema |
| **Straight-through processing (STP) rate** | N/A | >= 75% of docs auto-delivered (HIGH confidence, no human review) | >= 85% | `(PASS docs / total docs)` in metrics |
| **End-to-end latency p95** | N/A | < 15s for 2-page PDF (STP path) | < 10s | Prometheus histogram `ocr_extraction_duration_seconds` |
| **Throughput** | N/A | 100 docs/min per tenant | 500 docs/min per tenant | Load test + Prometheus counter |
| **Cost per document** | N/A | < $0.05 (LLM tokens + infra) | < $0.03 (with model routing) | `(monthly LLM cost + infra cost) / docs_processed` |
| **Human review rate** | N/A | <= 20% of docs require review | <= 10% | `(MEDIUM confidence docs / total docs)` |
| **Time to onboard a new doc type** | Days–weeks (bespoke build) | < 1 business day (with 10 seed examples) | < 2 hours | Measured in tenant onboarding sessions |
| **Dead-letter rate** | N/A | < 2% of all documents | < 0.5% | `(DLQ docs / total docs)` |

---

## 8. Phased Roadmap & MVP Scope

### MVP — Phase 1 (Sprint 1–4, ~8 weeks)

**Goal:** Invoice extraction working end-to-end for one pilot tenant. Prove the stateful pipeline, guardrails, and human review loop.

**Must ship:**
- F-01 Ingestion API (REST, single-doc)
- F-02 LlamaParse document parsing (PDF + DOCX)
- F-03 LangGraph extraction workflow (invoice schema hardcoded in Phase 1; schema registry in Phase 2)
- F-04 LLM extraction via LangChain (Claude default, GPT-4o as secondary)
- F-05 Qdrant vector DB with few-shot RAG (manual seed upload via admin script in Phase 1)
- F-06 Full guardrail pipeline (ported and generalized from `cv-batch-extractor`)
- F-07 Confidence scoring
- F-08 Human-in-the-loop review UI (minimal — review queue list + field editor, no PDF embed yet)
- F-10 Webhook delivery
- F-11 Multi-tenancy (2 tenants max at MVP, row-level isolation)
- F-12 Audit log
- F-13 Dead-letter queue

**Explicitly deferred (not in Phase 1):**
- F-09 Schema Registry UI — Document Engineers use admin API/script in Phase 1
- F-14 Deduplication — reason: low priority until doc volume is high
- F-15 Batch API — reason: single-doc sufficient for pilot
- F-17 Multi-modal vision path — reason: LlamaParse covers 90% of invoice formats
- F-20 SSO/SAML — reason: API key auth sufficient for pilot
- F-21 Data residency controls — reason: single-region deployment at MVP
- PDF viewer in review UI — reason: link to source file is sufficient for pilot

### Phase 2 (Sprint 5–8, ~8 weeks)

**Goal:** Self-service schema onboarding (UC-003). Second doc type (purchase orders). Production-grade observability. 5 tenants.

**Ships:**
- F-09 Schema Registry (full UI + API)
- F-14 Deduplication
- F-15 Batch API
- F-16 Active learning loop
- PDF viewer in review UI
- Prometheus + Grafana dashboard
- OpenTelemetry tracing
- F-18 Prompt A/B testing (basic)

### Phase 3 (Sprint 9–12, ~8 weeks)

**Goal:** Enterprise readiness. Unlimited tenants. Data residency. Cost optimization.

**Ships:**
- F-17 Multi-modal vision path
- F-19 Cost optimization / model routing
- F-20 SSO/SAML/OIDC
- F-21 Data residency controls
- GDPR erasure workflow
- SLA monitoring dashboard for Tenant Admins

---

## 9. Open Questions & Risks

| # | Question | Recommended default / decision needed | Owner | Due |
|---|----------|--------------------------------------|-------|-----|
| OQ-01 | **LlamaParse API vs self-hosted?** | Use LlamaParse cloud API at MVP (fastest path). Evaluate self-hosted `llama_parse` OSS for Phase 2 if data residency or cost is a concern. | Tenant Admin / Platform Operator | Sprint 1 kickoff |
| OQ-02 | **Vector DB choice: Qdrant vs Weaviate vs pgvector?** | Recommend Qdrant: best performance/simplicity ratio, native multi-tenancy via collections, Docker-native. Use pgvector only if you want zero new infra. Weaviate adds complexity without proportional gain at this scale. | Platform Operator | Sprint 1 kickoff |
| OQ-03 | **LLM provider data processing agreements (DPAs)?** | If any tenant processes personal data (names, addresses on invoices), a signed DPA with Anthropic/OpenAI is required before production go-live. Block Phase 1 production launch on this. | Compliance Officer | Before pilot launch |
| OQ-04 | **On-premise / private cloud deployment required?** | If yes, all LLM calls must route to a self-hosted model (e.g. Llama 3 via vLLM). This changes the LLM abstraction from LangChain cloud providers to local inference. Significant infra cost. Flag immediately if any pilot tenant requires this. | Tenant Admin | Sprint 1 |
| OQ-05 | **Human review SLA: 24h notification enough?** | Recommendation: 24h default, configurable per tenant (e.g. 4h for high-volume tenants). Confirm with first pilot tenant. | Product / Pilot Tenant | Sprint 2 |
| OQ-06 | **Invoice schema: which fields are REQUIRED vs optional?** | Recommend: `invoiceNumber`, `invoiceDate`, `vendorName`, `totalAmount`, `currency` as REQUIRED (BLOCK if missing). All others WARN. Validate with pilot tenant before schema v1 is frozen. | Document Engineer | Sprint 1 |
| OQ-07 | **LangGraph state persistence backend?** | Recommend PostgreSQL (via `langgraph-checkpoint-postgres`) as the single state store — avoids introducing Redis at MVP. Reassess if latency requirements tighten. | Platform Operator | Sprint 1 |
| OQ-08 | **Correction-to-few-shot promotion: immediate or gated?** | MVP recommendation: immediate write to vector DB (simple). Risk: a bad correction poisons future extractions. Phase 2 should gate on Document Engineer approval. Flag this as a known Phase 2 upgrade path. | Product | Sprint 3 planning |
| OQ-09 | **Pricing model: per document or per tenant flat rate?** | Out of scope for this spec but needed before first commercial contract. Suggest: base tenant fee + per-document tier above a monthly threshold. | Commercial/Finance | Before Phase 2 |

---

## Appendix A — System Component Map

```
                  ┌──────────────────────────────────────────┐
                  │              API Gateway                  │
                  │  (FastAPI, JWT auth, tenant middleware)   │
                  └────────────┬─────────────────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │        Ingestion Service         │
              │  (REST endpoint / S3 watcher)    │
              └────────────────┬────────────────┘
                               │  document_id + raw file
              ┌────────────────▼────────────────┐
              │     LangGraph Workflow Engine    │
              │  ┌──────────────────────────┐   │
              │  │  1. parse_node           │◄──┼── LlamaParse API
              │  │  2. input_guard_node     │   │
              │  │  3. extract_node         │◄──┼── LangChain → LLM
              │  │     (RAG few-shot)       │◄──┼── Qdrant Vector DB
              │  │  4. output_guard_node    │   │
              │  │  5. route_node           │   │
              │  └──────────────────────────┘   │
              │  State persisted → PostgreSQL    │
              └────────────────┬────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
   ┌──────▼──────┐    ┌────────▼────────┐   ┌──────▼──────┐
   │  Webhook    │    │  Human Review   │   │  Dead-Letter │
   │  Delivery   │    │  Queue (UI)     │   │  Queue       │
   └──────┬──────┘    └────────┬────────┘   └─────────────┘
          │                    │ corrections
          │                    ▼
          │           ┌────────────────┐
          │           │  Qdrant        │
          │           │  (few-shot DB) │
          │           └────────────────┘
          │
   ┌──────▼──────────────────────────────┐
   │           Audit Log                  │
   │  (append-only PostgreSQL table)      │
   └──────────────────────────────────────┘
```

---

## Appendix B — Technology Decisions (Recommended Defaults)

| Concern | Recommended choice | Rationale |
|---------|-------------------|-----------|
| API framework | FastAPI + Uvicorn | Async, fast, native Pydantic integration |
| LLM orchestration | LangChain (LCEL) | Provider-agnostic; large ecosystem; works natively with LangGraph |
| Workflow engine | LangGraph | Stateful DAG with checkpointing; purpose-built for multi-step LLM pipelines |
| PDF/image parsing | LlamaParse (cloud API) | Best-in-class structured output from complex PDFs, tables, scanned docs |
| Vector DB | Qdrant | Multi-tenant collections, fast ANN, simple Docker deploy, Python client |
| Primary LLM | Anthropic Claude claude-sonnet-4-6 | Strong structured extraction, function calling, JSON mode |
| Fallback LLM | OpenAI GPT-4o | Coverage if Anthropic is unavailable |
| Relational DB | PostgreSQL 16 | Audit log (append-only), schema registry, LangGraph state, row-level security |
| Workflow state | langgraph-checkpoint-postgres | Single DB, no Redis dependency at MVP |
| Schema validation | Pydantic v2 | Fast, battle-tested, used in prior art |
| Containerization | Docker Compose (dev) → Kubernetes (prod) | Simple local dev; K8s for production scaling |
| Observability | Prometheus + Grafana + OpenTelemetry | Standard enterprise stack; no vendor lock-in |
