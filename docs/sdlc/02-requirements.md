# Requirements — Enterprise OCR / Document Extraction Platform
**Date:** 2026-06-09  **Author:** @requirements-analyst  **Status:** REVIEWED
**Source:** `docs/sdlc/01-product-spec.md`

---

## Formal Requirements

### US-001: Invoice Extraction — Straight-Through Processing

| ID | Requirement (testable statement) | Priority | Source Story |
|----|----------------------------------|----------|-------------|
| REQ-001 | System shall accept a POST to `/api/v1/extract` with a valid PDF (<=50 MB), `document_type`, and valid tenant API key, and return HTTP 202 with `document_id` within 500 ms | MUST | US-001 |
| REQ-002 | System shall complete the STP pipeline (LlamaParse -> LangGraph -> LLM extraction -> guardrails -> webhook) within 15 s (p95) for a standard 2-page machine-readable invoice | MUST | US-001 |
| REQ-003 | System shall route HIGH-confidence results (>=0.85) directly to webhook delivery with no human review | MUST | US-001 |
| REQ-004 | Extracted invoice JSON shall contain required fields: `invoiceNumber`, `invoiceDate`, `vendorName`, `totalAmount`, `currency`; any missing required field forces `confidence: LOW` | MUST | US-001 |
| REQ-005 | System shall deliver a webhook callback for every extraction outcome (PASS / DEGRADED / REJECTED / ERROR) — the platform never silently drops a document | MUST | US-001 |
| REQ-006 | System shall return HTTP 422 `UNSUPPORTED_FILE_TYPE` for non-PDF/non-image file types (e.g., .exe, .zip) | MUST | US-001 |
| REQ-007 | System shall return HTTP 413 when uploaded file exceeds 50 MB | MUST | US-001 |
| REQ-008 | System shall validate the `document_type` parameter against registered schemas; unknown types return HTTP 422 `UNKNOWN_DOCUMENT_TYPE` | MUST | US-001 |
| REQ-009 | System shall route MEDIUM-confidence results (0.60..0.84) to the human review queue | MUST | US-001, US-002 |
| REQ-010 | System shall route LOW-confidence results (<0.60) to the DLQ with `failure_reason: LOW_CONFIDENCE` | MUST | US-001, US-006 |
| REQ-011 | Webhook payloads shall be signed with HMAC-SHA256 using the tenant's webhook secret | MUST | US-001 |
| REQ-012 | System shall retry failed webhook deliveries with exponential backoff (1 s, 5 s, 30 s, 120 s, 600 s) up to 5 attempts before writing to DLQ | MUST | US-001, US-006 |
| REQ-013 | System shall run prompt injection detection on all extracted text before it reaches the LLM | MUST | US-001, US-004 |

### US-002: Human-in-the-Loop Review

| ID | Requirement | Priority | Source Story |
|----|-------------|----------|-------------|
| REQ-014 | MEDIUM-confidence documents shall appear in the review queue within 60 seconds of pipeline completion | MUST | US-002 |
| REQ-015 | Review queue item shall display extracted JSON fields in an editable form plus a link to the original document | MUST | US-002 |
| REQ-016 | On Accept/Correct, system shall save corrections, fire the webhook with the updated result, and write the corrected record to Qdrant as a new few-shot example scoped to the tenant | MUST | US-002 |
| REQ-017 | Every review action (accept / correct / reject) shall be recorded in the audit log with `reviewer_id`, `timestamp`, `action`, `changed_fields` | MUST | US-002, US-005 |
| REQ-018 | Review items older than 24 h shall trigger a notification to the Tenant Admin via configured channel (email or Slack) | MUST | US-002 |
| REQ-019 | System shall enforce optimistic locking on review items — if two reviewers attempt to accept the same item, the second receives HTTP 409 Conflict | MUST | US-002 |
| REQ-020 | A reviewer shall only see review items belonging to their own tenant | MUST | US-002, US-004 |

### US-003: Self-Service Document Type Onboarding

| ID | Requirement | Priority | Source Story |
|----|-------------|----------|-------------|
| REQ-021 | POST to `/api/v1/schemas` with a valid JSON Schema shall create a schema with `status: draft` and a generated prompt template within 5 s | MUST | US-003 |
| REQ-022 | Upload of at least 3 labelled seed documents via `/api/v1/schemas/{id}/examples` shall index them in the tenant's Qdrant collection | MUST | US-003 |
| REQ-023 | A dry-run extraction (`dry_run=true`) shall return extracted JSON + confidence without persisting results or triggering webhooks | MUST | US-003 |
| REQ-024 | PATCH schema `status: draft -> active` shall make it available for live extraction with no redeployment | MUST | US-003 |
| REQ-025 | Publishing a new schema version shall preserve the old version; in-flight documents complete on the version they started | MUST | US-003 |
| REQ-026 | System shall reject schema activation if fewer than 3 seed examples are indexed | MUST | US-003 |
| REQ-027 | Seed examples shall be tenant-scoped; a schema in Tenant A shall never retrieve examples from Tenant B | MUST | US-003, US-004 |

### US-004: Multi-Tenant Isolation & API Key Management

| ID | Requirement | Priority | Source Story |
|----|-------------|----------|-------------|
| REQ-028 | Any API request with a JWT missing or containing an invalid `tenant_id` claim shall receive HTTP 401 | MUST | US-004 |
| REQ-029 | All tenant-data queries shall be filtered by `tenant_id` enforced at PostgreSQL RLS — not application code alone | MUST | US-004 |
| REQ-030 | Every Qdrant query shall include a `tenant_id` filter; a query missing this filter shall be rejected at the service layer before execution | MUST | US-004 |
| REQ-031 | PII fields declared in `pii_fields[]` shall be AES-256 encrypted at rest in PostgreSQL and replaced with `[REDACTED]` in all log output | MUST | US-004 |
| REQ-032 | POST to `/api/v1/admin/api-keys` shall create a scoped API key with optional `description` and optional `expires_at`; revoked keys return HTTP 401 within 100 ms | MUST | US-004 |
| REQ-033 | LLM prompt context shall never include examples or results from a different tenant | MUST | US-004 |
| REQ-034 | JWT tokens shall use RS256 signing; all API traffic over TLS 1.2+ | MUST | US-004 |
| REQ-035 | System shall return HTTP 429 with `Retry-After` header when a tenant's queue exceeds `max_queue_size` (default 500) | MUST | US-004 |

### US-005: Audit Trail & Compliance Export

| ID | Requirement | Priority | Source Story |
|----|-------------|----------|-------------|
| REQ-036 | Every pipeline event (ingest / guard / LLM call / delivery / review) shall produce an audit record with `tenant_id`, `document_id`, `event_type`, `actor`, `timestamp`, `status`, SHA-256 payload hash | MUST | US-005 |
| REQ-037 | The audit table shall reject all UPDATE and DELETE operations via a PostgreSQL trigger; any attempt returns an error | MUST | US-005 |
| REQ-038 | GET `/api/v1/audit?from=&to=` shall return the tenant's audit log as NDJSON or CSV within 30 s for up to 90 days of history | MUST | US-005 |
| REQ-039 | GDPR erasure via DELETE `/api/v1/documents/{id}` shall hard-delete document content, PII fields, and Qdrant vectors; a tombstone audit record (metadata only, no content) shall remain | MUST | US-005 |
| REQ-040 | A nightly purge job shall delete documents older than the tenant's configured retention period (default 90 days); purge events shall be logged in the audit trail | MUST | US-005 |
| REQ-041 | GDPR erasure of a document currently in-flight shall cancel the pipeline run, discard partial state, hard-delete all content, and record a tombstone | MUST | US-005 |

### US-006: Dead-Letter Queue & Observability

| ID | Requirement | Priority | Source Story |
|----|-------------|----------|-------------|
| REQ-042 | GET `/metrics` shall expose: `ocr_documents_ingested_total`, `ocr_documents_completed_total`, `ocr_documents_rejected_total`, `ocr_extraction_duration_seconds` (histogram), `ocr_llm_tokens_used_total`, `ocr_review_queue_depth` | MUST | US-006 |
| REQ-043 | Documents reaching REJECTED or ERROR status shall be written to the DLQ with `document_id`, `tenant_id`, `failure_reason`, `pipeline_state`, `timestamp` | MUST | US-006 |
| REQ-044 | GET `/api/v1/admin/dlq` shall return a paginated list filterable by tenant and status | MUST | US-006 |
| REQ-045 | POST `/api/v1/admin/dlq/{id}/retry` shall re-enter the document into the pipeline from the start | MUST | US-006 |
| REQ-046 | LLM circuit breaker (5 failures in 60 s) shall fire an alert within 2 minutes via configured alerting channel | MUST | US-006 |
| REQ-047 | When LLM circuit breaker is OPEN, system shall attempt the fallback LLM (GPT-4o); if fallback also fails, document goes to DLQ with `failure_reason: LLM_UNAVAILABLE` | MUST | US-006 |
| REQ-048 | Default alerts shall fire for: DLQ depth > 50 for 5 min, circuit breaker OPEN, p95 latency > 30 s, error rate > 5% | MUST | US-006 |
| REQ-049 | Webhook retry exhaustion (5 attempts failed) shall write the document to DLQ with `failure_reason: WEBHOOK_DELIVERY_FAILED` and the last HTTP status code | MUST | US-006 |
| REQ-050 | DLQ retry shall be idempotent — retrying an already-retried or resolved item shall return HTTP 409 | MUST | US-006 |

### Cross-Cutting / NFR Requirements

| ID | Requirement | Priority | Source Story |
|----|-------------|----------|-------------|
| REQ-051 | System shall support 100 docs/min per tenant and 1,000 docs/min platform-wide | MUST | NFR |
| REQ-052 | Async worker pool with configurable concurrency per tenant (default 10); LangGraph state persisted to PostgreSQL via langgraph-checkpoint-postgres | MUST | NFR |
| REQ-053 | Structured JSON logs on every pipeline step with `tenant_id`, `document_id`, `event`, `duration_ms`, `model_used`, `token_usage` | MUST | NFR |
| REQ-054 | Configurable document retention per tenant (default 90 days) | MUST | NFR |
| REQ-055 | Confidence thresholds (HIGH >= 0.85, MEDIUM 0.60..0.84, LOW < 0.60) shall be configurable per schema | MUST | NFR |

---

## Acceptance Criteria (Gherkin)

### Feature: Invoice Extraction (US-001)

```gherkin
Feature: Invoice Extraction — Straight-Through Processing

  # --- Happy Path ---

  Scenario: SC-001 Successful invoice submission returns 202
    Given a tenant with a valid API key
    And the tenant has the "invoice" document type active
    When the tenant POSTs a 2-page PDF invoice (< 50 MB) to /api/v1/extract with document_type=invoice
    Then the API returns HTTP 202 within 500 ms
    And the response body contains a unique document_id

  Scenario: SC-002 HIGH-confidence invoice delivered via webhook (STP)
    Given a submitted invoice document_id in the pipeline
    And the extraction result has confidenceOverall >= 0.85
    And all required fields (invoiceNumber, invoiceDate, vendorName, totalAmount, currency) are present
    When the pipeline completes
    Then the webhook fires within 15 seconds (p95)
    And the payload contains all extracted fields with status PASS
    And the payload is signed with HMAC-SHA256
    And no review queue item is created

  Scenario: SC-003 MEDIUM-confidence invoice routed to review queue
    Given a submitted invoice document_id in the pipeline
    And the extraction result has confidenceOverall between 0.60 and 0.84
    When the pipeline completes
    Then the document appears in the review queue within 60 seconds
    And a webhook fires with status DEGRADED and confidence details

  Scenario: SC-004 LOW-confidence invoice routed to DLQ
    Given a submitted invoice document_id in the pipeline
    And the extraction result has confidenceOverall < 0.60
    When the pipeline completes
    Then the document is written to the DLQ with failure_reason LOW_CONFIDENCE
    And a webhook fires with status REJECTED

  # --- Error & Edge Cases ---

  Scenario: SC-005 Missing required field forces LOW confidence
    Given a submitted invoice where the LLM extraction omits invoiceNumber
    When the confidence scoring runs
    Then confidenceOverall is set to LOW regardless of other scores
    And lowConfidenceFields includes "invoiceNumber"
    And the document routes to the DLQ

  Scenario: SC-006 Unsupported file type rejected at ingest
    Given a tenant with a valid API key
    When the tenant POSTs a .exe file to /api/v1/extract
    Then the API returns HTTP 422 with error code UNSUPPORTED_FILE_TYPE
    And no pipeline processing is started
    And an audit record is created with event_type INGEST_REJECTED

  Scenario: SC-007 Oversized file rejected at ingest
    Given a tenant with a valid API key
    When the tenant POSTs a 55 MB PDF to /api/v1/extract
    Then the API returns HTTP 413
    And no pipeline processing is started

  Scenario: SC-008 Unknown document_type rejected at ingest
    Given a tenant with a valid API key
    When the tenant POSTs a PDF with document_type=unknown_type
    Then the API returns HTTP 422 with error code UNKNOWN_DOCUMENT_TYPE

  Scenario: SC-009 Prompt injection detected in extracted text
    Given a submitted document whose extracted text contains prompt injection patterns
    When the guardrail step runs
    Then the document is flagged with guardrail_result BLOCK
    And the document is written to the DLQ with failure_reason INJECTION_DETECTED
    And an audit record is created with event_type GUARDRAIL_BLOCK
    And the flagged text never reaches the LLM

  Scenario: SC-010 Confidence exactly at 0.85 boundary
    Given a submitted invoice with confidenceOverall = 0.85 (exact)
    When the confidence routing runs
    Then the document is routed as HIGH confidence (STP path)
    And the webhook fires with status PASS

  Scenario: SC-011 Confidence exactly at 0.60 boundary
    Given a submitted invoice with confidenceOverall = 0.60 (exact)
    When the confidence routing runs
    Then the document is routed as MEDIUM confidence (review queue)
    And the webhook fires with status DEGRADED

  Scenario: SC-012 Tenant queue at capacity returns 429
    Given tenant A has 500 documents queued (max_queue_size reached)
    When tenant A POSTs another document to /api/v1/extract
    Then the API returns HTTP 429 with Retry-After header
    And no new pipeline work is enqueued
```

### Feature: Human-in-the-Loop Review (US-002)

```gherkin
Feature: Human-in-the-Loop Review Queue

  Scenario: SC-013 Reviewer sees only own tenant's items
    Given reviewer belongs to Tenant A
    And there are review items for Tenant A and Tenant B
    When the reviewer fetches the review queue
    Then only Tenant A items are returned

  Scenario: SC-014 Reviewer corrects a field and accepts
    Given a MEDIUM-confidence document in Tenant A's review queue
    When the reviewer edits the vendorName field and clicks Accept
    Then the corrected result is saved to the document record
    And a webhook fires with the updated extraction and status PASS
    And the corrected record is written to Qdrant as a few-shot example with tenant_id = Tenant A
    And an audit record is created with action REVIEW_ACCEPT, reviewer_id, and changed_fields

  Scenario: SC-015 Reviewer rejects a document
    Given a MEDIUM-confidence document in the review queue
    When the reviewer clicks Reject with a rejection reason
    Then the document status is set to REJECTED
    And a webhook fires with status REJECTED
    And an audit record is created with action REVIEW_REJECT

  Scenario: SC-016 Concurrent reviewers — optimistic locking
    Given a review queue item being viewed by Reviewer X and Reviewer Y simultaneously
    When Reviewer X accepts the item first
    And Reviewer Y then attempts to accept the same item
    Then Reviewer Y receives HTTP 409 Conflict
    And only Reviewer X's changes are persisted

  Scenario: SC-017 Stale review item triggers notification
    Given a review item has been in the queue for 24 hours
    When the notification scheduler runs
    Then the Tenant Admin receives a notification via configured channel
    And the notification includes document_id and queue age

  Scenario: SC-018 Correction writes tenant-scoped few-shot example
    Given a reviewer in Tenant A corrects and accepts a document
    When the system writes the correction to Qdrant
    Then the vector record includes tenant_id = Tenant A
    And a subsequent extraction for Tenant B does not retrieve this example
```

### Feature: Self-Service Schema Onboarding (US-003)

```gherkin
Feature: Self-Service Document Type Onboarding

  Scenario: SC-019 Register a new schema
    Given a Document Engineer for Tenant A
    When they POST a valid JSON Schema to /api/v1/schemas
    Then the schema is created with status draft
    And a prompt template is auto-generated within 5 seconds
    And the schema is scoped to Tenant A

  Scenario: SC-020 Upload seed examples
    Given a draft schema for Tenant A
    When the Document Engineer uploads 3 labelled seed documents
    Then all 3 are indexed in Tenant A's Qdrant collection
    And each vector record includes tenant_id and schema_id

  Scenario: SC-021 Dry-run extraction
    Given a draft schema with 3 seed examples
    When a dry-run extraction is requested
    Then the result contains extracted JSON and confidence scores
    And no results are persisted to the database
    And no webhook is triggered
    And no audit trail is written for the extraction itself

  Scenario: SC-022 Activate schema
    Given a draft schema with at least 3 seed examples
    When the Document Engineer PATCHes status to active
    Then the schema is available for live extraction
    And no platform redeployment is required

  Scenario: SC-023 Activate schema with insufficient seeds rejected
    Given a draft schema with only 2 seed examples
    When the Document Engineer PATCHes status to active
    Then the API returns HTTP 422 with error INSUFFICIENT_SEED_EXAMPLES
    And the schema remains in draft status

  Scenario: SC-024 Schema versioning preserves in-flight documents
    Given schema v1 is active and document D is mid-extraction using v1
    When the Document Engineer publishes schema v2
    Then document D completes extraction using v1
    And new submissions use v2
    And v1 remains queryable for audit purposes
```

### Feature: Multi-Tenant Isolation (US-004)

```gherkin
Feature: Multi-Tenant Isolation & API Key Management

  Scenario: SC-025 Invalid JWT rejected
    Given an API request with a JWT missing tenant_id claim
    When the request reaches any endpoint
    Then the API returns HTTP 401
    And no data is accessed

  Scenario: SC-026 PostgreSQL RLS enforces tenant boundary
    Given Tenant A and Tenant B each have documents in the database
    When Tenant A queries /api/v1/documents
    Then only Tenant A's documents are returned
    And this is enforced by PostgreSQL RLS, not application WHERE clause alone

  Scenario: SC-027 Qdrant query without tenant filter rejected
    Given an internal service attempts a Qdrant query
    When the query payload does not include a tenant_id filter
    Then the Qdrant service layer rejects the query before execution
    And an error is logged with severity CRITICAL

  Scenario: SC-028 Cross-tenant vector leakage prevented
    Given Tenant A has 50 seed examples in Qdrant
    And Tenant B has 30 seed examples in Qdrant
    When Tenant B performs an extraction that triggers RAG lookup
    Then only Tenant B's 30 examples are candidates for retrieval
    And zero of Tenant A's examples appear in the LLM prompt context

  Scenario: SC-029 PII fields encrypted and masked
    Given a schema declaring vendorTaxId in pii_fields[]
    When an extraction produces vendorTaxId = "123-45-6789"
    Then the value is AES-256 encrypted at rest in PostgreSQL
    And all log entries show vendorTaxId as [REDACTED]

  Scenario: SC-030 Create and revoke API key
    Given a Tenant Admin for Tenant A
    When they POST to /api/v1/admin/api-keys with description and expires_at
    Then a new API key is created scoped to Tenant A
    And when the key is revoked via DELETE /api/v1/admin/api-keys/{id}
    Then requests using the revoked key return HTTP 401 within 100 ms

  Scenario: SC-031 Expired API key rejected
    Given an API key for Tenant A with expires_at = yesterday
    When a request is made using this key
    Then the API returns HTTP 401
    And the audit log records AUTH_EXPIRED
```

### Feature: Audit Trail & Compliance (US-005)

```gherkin
Feature: Audit Trail & Compliance Export

  Scenario: SC-032 Pipeline event produces audit record
    Given a document is ingested for Tenant A
    When the pipeline progresses through ingest, guard, LLM call, and delivery
    Then an audit record is created for each step
    And each record contains tenant_id, document_id, event_type, actor, timestamp, status, and SHA-256 payload hash

  Scenario: SC-033 Audit table rejects UPDATE
    Given an existing audit record
    When a database client attempts to UPDATE the record
    Then the PostgreSQL trigger rejects the operation with an error
    And the original record is unchanged

  Scenario: SC-034 Audit table rejects DELETE
    Given an existing audit record
    When a database client attempts to DELETE the record
    Then the PostgreSQL trigger rejects the operation with an error
    And the original record is unchanged

  Scenario: SC-035 Audit export within 30 seconds
    Given Tenant A has 90 days of audit history
    When the Compliance Officer calls GET /api/v1/audit?from=2026-03-01&to=2026-06-01
    Then the response is returned within 30 seconds
    And the format is NDJSON or CSV (per Accept header)
    And only Tenant A's records are included

  Scenario: SC-036 GDPR erasure — document at rest
    Given document D belongs to Tenant A and is fully processed
    When the Compliance Officer calls DELETE /api/v1/documents/{D}
    Then all document content and PII fields are hard-deleted from PostgreSQL
    And all vectors for document D are deleted from Qdrant
    And a tombstone audit record is created (event metadata only, no content)
    And the tombstone is exempt from the audit DELETE trigger

  Scenario: SC-037 GDPR erasure — document in-flight
    Given document D is currently mid-pipeline (e.g., awaiting LLM response)
    When the Compliance Officer calls DELETE /api/v1/documents/{D}
    Then the pipeline run is cancelled
    And partial LangGraph state for document D is purged from the checkpoint table
    And all content and PII are hard-deleted
    And a tombstone audit record is created with event_type ERASURE_IN_FLIGHT

  Scenario: SC-038 Nightly purge removes expired documents
    Given Tenant A has retention_period = 90 days
    And there are documents older than 90 days
    When the nightly purge job runs
    Then those documents' content and PII are deleted
    And tombstone audit records are created for each purged document
    And vectors in Qdrant for those documents are deleted
```

### Feature: Dead-Letter Queue & Observability (US-006)

```gherkin
Feature: Dead-Letter Queue & Observability

  Scenario: SC-039 Prometheus metrics endpoint
    Given the platform is running
    When a client scrapes GET /metrics
    Then the response includes ocr_documents_ingested_total, ocr_documents_completed_total, ocr_documents_rejected_total, ocr_extraction_duration_seconds, ocr_llm_tokens_used_total, ocr_review_queue_depth
    And all counters are labeled with tenant_id

  Scenario: SC-040 Failed document written to DLQ
    Given a document reaches ERROR status due to an unhandled exception
    When the error handler runs
    Then the document is written to the DLQ with document_id, tenant_id, failure_reason, pipeline_state snapshot, and timestamp
    And an audit record is created with event_type DLQ_ENTRY

  Scenario: SC-041 DLQ listing with filters
    Given the DLQ contains items for Tenant A and Tenant B
    When a Platform Operator calls GET /api/v1/admin/dlq?tenant_id=A&status=pending
    Then only matching items are returned
    And the list is paginated

  Scenario: SC-042 DLQ retry re-enters pipeline
    Given a DLQ item with status pending
    When a Platform Operator calls POST /api/v1/admin/dlq/{id}/retry
    Then the document re-enters the pipeline from the start
    And the DLQ item status changes to retrying
    And an audit record is created with event_type DLQ_RETRY

  Scenario: SC-043 DLQ retry idempotency
    Given a DLQ item that has already been retried (status = retrying or resolved)
    When a Platform Operator calls POST /api/v1/admin/dlq/{id}/retry
    Then the API returns HTTP 409 Conflict
    And no duplicate pipeline run is started

  Scenario: SC-044 LLM circuit breaker opens and fallback activates
    Given the primary LLM (Claude) has failed 5 times in 60 seconds
    When the circuit breaker opens
    Then an alert fires within 2 minutes via the configured channel
    And subsequent extraction requests are routed to the fallback LLM (GPT-4o)
    And an audit record is created with event_type CIRCUIT_BREAKER_OPEN

  Scenario: SC-045 Both LLMs unavailable — DLQ
    Given the primary LLM circuit breaker is OPEN
    And the fallback LLM also fails
    When a document is being extracted
    Then the document is written to the DLQ with failure_reason LLM_UNAVAILABLE
    And a webhook fires with status ERROR

  Scenario: SC-046 Webhook retry exhaustion
    Given a document extraction completed successfully
    And the tenant's webhook endpoint is unreachable
    When the system retries delivery 5 times (1s, 5s, 30s, 120s, 600s)
    And all 5 attempts fail
    Then the document is written to the DLQ with failure_reason WEBHOOK_DELIVERY_FAILED and the last HTTP status code
    And an audit record is created with event_type WEBHOOK_EXHAUSTED

  Scenario: SC-047 Default alert thresholds
    Given the platform is running with default alert configuration
    When DLQ depth exceeds 50 for 5 minutes
    Then an alert fires
    When the error rate exceeds 5%
    Then an alert fires
    When p95 latency exceeds 30 seconds
    Then an alert fires
```

### Feature: LangGraph Workflow Resilience (Cross-Cutting)

```gherkin
Feature: LangGraph Workflow Failure Modes

  Scenario: SC-048 Mid-graph crash recovery via checkpoint
    Given a document is at the LLM extraction step in LangGraph
    And the worker process crashes unexpectedly
    When the worker restarts
    Then the document's LangGraph state is recovered from the PostgreSQL checkpoint
    And the pipeline resumes from the last completed step
    And no duplicate LLM calls are made for already-completed steps

  Scenario: SC-049 LlamaParse failure — retry then DLQ
    Given a document is submitted for extraction
    When LlamaParse returns an error (HTTP 5xx or timeout)
    Then the system retries the parse up to 3 times with exponential backoff
    And if all retries fail, the document is written to the DLQ with failure_reason PARSE_FAILED
    And a webhook fires with status ERROR

  Scenario: SC-050 LlamaParse returns empty/corrupt output
    Given a document is submitted and LlamaParse returns an empty string or malformed output
    When the guardrail step validates the parse output
    Then the document is flagged with guardrail_result BLOCK
    And the document is written to the DLQ with failure_reason PARSE_EMPTY_OUTPUT
    And the raw output is preserved in the DLQ record for debugging

  Scenario: SC-051 Partial LangGraph state on timeout
    Given a document's LangGraph execution exceeds the per-document timeout (default 60s)
    When the timeout fires
    Then the pipeline is cancelled gracefully
    And the partial state is preserved in the DLQ record
    And the document is written to the DLQ with failure_reason PIPELINE_TIMEOUT
    And the webhook fires with status ERROR
```

---

## Edge Cases Identified

| EC-ID | Scenario description | Required handling |
|-------|---------------------|------------------|
| EC-001 | Cross-tenant vector leakage: Qdrant query omits tenant_id filter | Service layer MUST reject query; log CRITICAL; never fall through to unfiltered search |
| EC-002 | LLM prompt receives examples from wrong tenant | Qdrant service layer enforces tenant_id on all queries; application layer double-checks tenant_id on returned vectors before injecting into prompt |
| EC-003 | Confidence score exactly at threshold boundary (0.60, 0.85) | 0.85 routes HIGH (>=), 0.60 routes MEDIUM (>=); boundaries are inclusive on the upper tier |
| EC-004 | Guardrail WARN vs BLOCK escalation | WARN: log + proceed with reduced confidence multiplier (0.8x); BLOCK: halt pipeline, DLQ entry, never send text to LLM |
| EC-005 | GDPR erasure request while document is mid-pipeline | Cancel pipeline, purge LangGraph checkpoint, hard-delete all content + PII, create tombstone; LLM provider may retain input in logs (see open issue I-001) |
| EC-006 | LlamaParse returns success but empty/malformed output | Text quality guardrail detects empty or malformed parse; routes to DLQ with PARSE_EMPTY_OUTPUT |
| EC-007 | Webhook endpoint returns 2xx but body indicates failure | System treats any HTTP 2xx as successful delivery; consumer-side failures are consumer's responsibility |
| EC-008 | Webhook retry exhaustion (5 attempts) | Write to DLQ with WEBHOOK_DELIVERY_FAILED + last HTTP status; Platform Operator can manually retry via DLQ API |
| EC-009 | Two reviewers accept same review item simultaneously | Optimistic locking (version column); second reviewer gets HTTP 409 Conflict |
| EC-010 | Correction-to-few-shot writes potentially incorrect example | MVP: immediate write (per open question 7); Phase 2: gate on Document Engineer approval. Risk: bad corrections pollute RAG. Mitigation: audit trail enables rollback |
| EC-011 | Schema version change while documents are in-flight | In-flight documents complete on the version they started (pinned at submission); new submissions use latest active version |
| EC-012 | LangGraph worker crash mid-execution | Checkpoint recovery from PostgreSQL; resume from last completed step; no duplicate LLM calls |
| EC-013 | LlamaParse cloud API rate-limited (HTTP 429) | Treat as transient failure; apply exponential backoff retry up to 3 times; circuit breaker separate from LLM circuit breaker |
| EC-014 | Nightly purge + GDPR erasure race condition | GDPR erasure is immediate and takes precedence; purge job skips documents already tombstoned; both operations are idempotent |
| EC-015 | API key rotated while requests are in-flight | In-flight requests authenticated at submission continue; new requests must use new key; revoked key returns 401 within 100 ms |
| EC-016 | Empty state: tenant with no schemas, no documents | API endpoints return empty lists (HTTP 200 with []) not errors; /api/v1/extract returns HTTP 422 UNKNOWN_DOCUMENT_TYPE if no schemas active |
| EC-017 | DLQ retry of a document whose schema has been deactivated | Retry should fail fast with failure_reason SCHEMA_DEACTIVATED; do not attempt extraction against a deactivated schema |
| EC-018 | Concurrent GDPR erasure and DLQ retry for the same document | Erasure wins; if retry starts before erasure completes, the pipeline detects the tombstone and aborts |

---

## Conflicts & Ambiguities Resolved

| # | Original ambiguity | Resolution | Decision owner |
|---|--------------------|-----------|---------------|
| C-001 | PM spec does not define what happens at exactly confidence = 0.60 or 0.85 | Boundaries are inclusive on the upper tier: >= 0.85 = HIGH, >= 0.60 = MEDIUM, < 0.60 = LOW | Requirements Analyst (default; PM to confirm) |
| C-002 | PM spec says "webhook always fires" but does not specify retry strategy | Exponential backoff: 1s, 5s, 30s, 120s, 600s (5 retries total); after exhaustion, DLQ + still fire one final webhook attempt with status ERROR | Requirements Analyst |
| C-003 | Guardrail result taxonomy (WARN vs BLOCK) not defined in PM spec | WARN = proceed with 0.8x confidence multiplier + log; BLOCK = halt pipeline, DLQ, never send to LLM | Requirements Analyst |
| C-004 | GDPR erasure while document in-flight not addressed by PM | Pipeline must be cancellable; partial checkpoint state purged; tombstone created; documented as REQ-041 | Compliance Officer |
| C-005 | DLQ retry idempotency not specified | Retry of already-retried/resolved item returns HTTP 409; prevents duplicate pipeline runs | Requirements Analyst |
| C-006 | PM spec lists LOW confidence routing but does not define destination | LOW confidence routes to DLQ (not review queue) — review queue is for MEDIUM only | Requirements Analyst (PM to confirm) |
| C-007 | Webhook payload on non-STP paths not specified | All paths fire webhook: PASS (HIGH/STP), DEGRADED (MEDIUM/review), REJECTED (LOW/DLQ or review-reject), ERROR (pipeline failure) | Requirements Analyst |
| C-008 | Per-document pipeline timeout not specified | Default 60s per document; configurable per schema; timeout routes to DLQ with PIPELINE_TIMEOUT | Requirements Analyst |
| C-009 | Schema activation minimum seed count not in PM spec | Minimum 3 seed examples required for activation (matches PM AC for uploads); activation with fewer returns HTTP 422 | Requirements Analyst |

---

## Out of Scope (explicit)

| Item | Reason excluded |
|------|----------------|
| SSO/SAML integration | Phase 3; API key auth sufficient for pilot |
| Embedded PDF viewer in review UI | Phase 2; link to source file sufficient at MVP |
| Multi-modal vision extraction path | Phase 2; LlamaParse covers 90%+ of invoice formats |
| Data residency / per-tenant region selection | Phase 3; single-region deployment at MVP |
| Cost optimization / model routing | Phase 3; validate accuracy first |
| ERP/SAP/QuickBooks push connectors | Webhook covers all downstream; connectors are customer-specific |
| Cross-tenant schema sharing | Phase 2 at earliest; isolation is paramount at MVP |
| Reviewer assignment routing | Phase 2; any tenant reviewer can pick up any item |
| Bulk-accept of multiple review items | Phase 2 convenience feature |
| OpenTelemetry distributed tracing | Phase 2; Prometheus + structured logs at MVP |
| Automated prompt generation from examples | Phase 2; manual prompt template at MVP |
| Duplicate invoice detection | Phase 2 SHOULD; not MVP MUST |

---

## Traceability Matrix

| REQ ID | User Story | Gherkin Scenario(s) | Notes |
|--------|-----------|---------------------|-------|
| REQ-001 | US-001 | SC-001 | Ingest endpoint |
| REQ-002 | US-001 | SC-002 | STP latency |
| REQ-003 | US-001 | SC-002, SC-010 | HIGH routing |
| REQ-004 | US-001 | SC-005 | Required fields |
| REQ-005 | US-001 | SC-002, SC-003, SC-004, SC-046 | Webhook always fires |
| REQ-006 | US-001 | SC-006 | File type validation |
| REQ-007 | US-001 | SC-007 | Size limit |
| REQ-008 | US-001 | SC-008 | Document type validation |
| REQ-009 | US-001, US-002 | SC-003, SC-011 | MEDIUM routing |
| REQ-010 | US-001, US-006 | SC-004, SC-005 | LOW routing to DLQ |
| REQ-011 | US-001 | SC-002 | HMAC signing |
| REQ-012 | US-001, US-006 | SC-046 | Webhook retry |
| REQ-013 | US-001, US-004 | SC-009 | Injection detection |
| REQ-014 | US-002 | SC-003 | Review queue timing |
| REQ-015 | US-002 | SC-014 | Review UI |
| REQ-016 | US-002 | SC-014, SC-018 | Correction flow |
| REQ-017 | US-002, US-005 | SC-014, SC-015 | Review audit |
| REQ-018 | US-002 | SC-017 | Stale item notification |
| REQ-019 | US-002 | SC-016 | Optimistic locking |
| REQ-020 | US-002, US-004 | SC-013 | Tenant-scoped review |
| REQ-021 | US-003 | SC-019 | Schema creation |
| REQ-022 | US-003 | SC-020 | Seed example upload |
| REQ-023 | US-003 | SC-021 | Dry-run extraction |
| REQ-024 | US-003 | SC-022 | Schema activation |
| REQ-025 | US-003 | SC-024 | Schema versioning |
| REQ-026 | US-003 | SC-023 | Minimum seeds |
| REQ-027 | US-003, US-004 | SC-018, SC-028 | Tenant-scoped seeds |
| REQ-028 | US-004 | SC-025 | JWT validation |
| REQ-029 | US-004 | SC-026 | PostgreSQL RLS |
| REQ-030 | US-004 | SC-027, SC-028 | Qdrant tenant filter |
| REQ-031 | US-004 | SC-029 | PII encryption |
| REQ-032 | US-004 | SC-030, SC-031 | API key lifecycle |
| REQ-033 | US-004 | SC-028 | LLM prompt isolation |
| REQ-034 | US-004 | SC-025 | TLS + RS256 |
| REQ-035 | US-004 | SC-012 | Rate limiting |
| REQ-036 | US-005 | SC-032 | Audit record creation |
| REQ-037 | US-005 | SC-033, SC-034 | Immutable audit |
| REQ-038 | US-005 | SC-035 | Audit export |
| REQ-039 | US-005 | SC-036 | GDPR erasure at rest |
| REQ-040 | US-005 | SC-038 | Nightly purge |
| REQ-041 | US-005 | SC-037 | GDPR erasure in-flight |
| REQ-042 | US-006 | SC-039 | Prometheus metrics |
| REQ-043 | US-006 | SC-040, SC-045 | DLQ entry |
| REQ-044 | US-006 | SC-041 | DLQ listing |
| REQ-045 | US-006 | SC-042 | DLQ retry |
| REQ-046 | US-006 | SC-044, SC-047 | Circuit breaker |
| REQ-047 | US-006 | SC-045 | LLM fallback |
| REQ-048 | US-006 | SC-047 | Alert thresholds |
| REQ-049 | US-006 | SC-046 | Webhook exhaustion DLQ |
| REQ-050 | US-006 | SC-043 | DLQ idempotency |
| REQ-051 | NFR | — | Throughput |
| REQ-052 | NFR | SC-048 | Worker pool + checkpoint |
| REQ-053 | NFR | — | Structured logs |
| REQ-054 | NFR | SC-038 | Retention |
| REQ-055 | NFR | SC-010, SC-011 | Configurable thresholds |

---

## Open Issues (blocking design)

| # | Issue | Impact if unresolved | Owner | Due |
|---|-------|---------------------|-------|-----|
| I-001 | LLM provider DPA: when PII is sent to LlamaParse cloud or Claude/GPT-4o, the provider may retain inputs in logs. GDPR erasure cannot guarantee deletion from provider-side logs. | Cannot launch with PII tenants; blocks pilot | Compliance Officer | Before pilot launch |
| I-002 | Invoice required-field set not confirmed with pilot tenant (default: invoiceNumber, invoiceDate, vendorName, totalAmount, currency) | Field F1 metric undefined until confirmed; may cause HIGH/LOW routing disagreements | Document Engineer | Sprint 1 |
| I-003 | LlamaParse cloud vs self-hosted decision affects architecture: cloud = simpler, self-hosted = data residency | Architecture diagram and deployment topology depend on this choice | Platform Operator | Sprint 1 kickoff |
| I-004 | On-premise deployment requirement from any pilot tenant changes LLM stack to vLLM | Entire LLM integration layer and fallback strategy changes | Tenant Admin | Sprint 1 |
| I-005 | Guardrail WARN confidence multiplier (0.8x proposed) needs validation with real extraction data | Incorrect multiplier could inflate STP rate (too high) or flood review queue (too low) | Document Engineer | Sprint 2 |
| I-006 | Correction-to-few-shot: immediate write at MVP risks polluting RAG with incorrect corrections | Bad corrections degrade future extractions for the entire tenant | Product | Sprint 3 planning |
| I-007 | Per-document pipeline timeout default (60s proposed) needs benchmarking against LlamaParse + LLM combined latency | Too short = false DLQ entries; too long = SLA breach | Platform Operator | Sprint 1 |
