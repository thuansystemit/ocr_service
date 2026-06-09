---
doc: 02-requirements
agent: requirements-analyst
phase: 1
status: complete
human_doc: 02-requirements.md
source: 01-product-spec
next: [architect]
provides:
  requirements:
    REQ-001: { p: MUST, story: US-001, text: "POST /api/v1/extract returns 202 with document_id within 500ms" }
    REQ-002: { p: MUST, story: US-001, text: "STP pipeline completes within 15s p95 for 2-page PDF" }
    REQ-003: { p: MUST, story: US-001, text: "HIGH confidence (>=0.85) routes to webhook, no review" }
    REQ-004: { p: MUST, story: US-001, text: "Required fields missing forces LOW confidence" }
    REQ-005: { p: MUST, story: US-001, text: "Webhook fires for every outcome (PASS/DEGRADED/REJECTED/ERROR)" }
    REQ-006: { p: MUST, story: US-001, text: "Unsupported file type returns 422" }
    REQ-007: { p: MUST, story: US-001, text: "Oversized file (>50MB) returns 413" }
    REQ-008: { p: MUST, story: US-001, text: "Unknown document_type returns 422" }
    REQ-009: { p: MUST, story: "US-001,US-002", text: "MEDIUM confidence (0.60-0.84) routes to review queue" }
    REQ-010: { p: MUST, story: "US-001,US-006", text: "LOW confidence (<0.60) routes to DLQ" }
    REQ-011: { p: MUST, story: US-001, text: "Webhook payloads HMAC-SHA256 signed" }
    REQ-012: { p: MUST, story: "US-001,US-006", text: "Webhook retry: 5 attempts exponential backoff then DLQ" }
    REQ-013: { p: MUST, story: "US-001,US-004", text: "Prompt injection detection before LLM" }
    REQ-014: { p: MUST, story: US-002, text: "MEDIUM docs appear in review queue within 60s" }
    REQ-015: { p: MUST, story: US-002, text: "Review UI shows editable fields + source link" }
    REQ-016: { p: MUST, story: US-002, text: "Accept/Correct saves, fires webhook, writes few-shot to Qdrant" }
    REQ-017: { p: MUST, story: "US-002,US-005", text: "Review actions audited with reviewer_id" }
    REQ-018: { p: MUST, story: US-002, text: "24h stale review item triggers notification" }
    REQ-019: { p: MUST, story: US-002, text: "Optimistic locking on review items (409 Conflict)" }
    REQ-020: { p: MUST, story: "US-002,US-004", text: "Reviewer sees only own tenant items" }
    REQ-021: { p: MUST, story: US-003, text: "POST /schemas creates draft schema with prompt in 5s" }
    REQ-022: { p: MUST, story: US-003, text: "3+ seed docs indexed in tenant Qdrant collection" }
    REQ-023: { p: MUST, story: US-003, text: "Dry-run returns JSON+confidence, no persist/webhook" }
    REQ-024: { p: MUST, story: US-003, text: "Schema activation requires no redeployment" }
    REQ-025: { p: MUST, story: US-003, text: "Schema versioning: in-flight docs complete on started version" }
    REQ-026: { p: MUST, story: US-003, text: "Activation blocked if <3 seed examples" }
    REQ-027: { p: MUST, story: "US-003,US-004", text: "Seed examples tenant-scoped in Qdrant" }
    REQ-028: { p: MUST, story: US-004, text: "JWT without valid tenant_id returns 401" }
    REQ-029: { p: MUST, story: US-004, text: "PostgreSQL RLS enforces tenant boundary" }
    REQ-030: { p: MUST, story: US-004, text: "Qdrant query without tenant_id filter rejected at service layer" }
    REQ-031: { p: MUST, story: US-004, text: "PII fields AES-256 encrypted at rest, [REDACTED] in logs" }
    REQ-032: { p: MUST, story: US-004, text: "API key create/revoke; revoked key 401 within 100ms" }
    REQ-033: { p: MUST, story: US-004, text: "LLM prompt never includes cross-tenant examples" }
    REQ-034: { p: MUST, story: US-004, text: "TLS 1.2+ and RS256 JWT" }
    REQ-035: { p: MUST, story: US-004, text: "HTTP 429 when tenant queue exceeds max_queue_size" }
    REQ-036: { p: MUST, story: US-005, text: "Audit record for every pipeline event with SHA-256 hash" }
    REQ-037: { p: MUST, story: US-005, text: "Audit table rejects UPDATE/DELETE via PG trigger" }
    REQ-038: { p: MUST, story: US-005, text: "Audit export NDJSON/CSV within 30s for 90 days" }
    REQ-039: { p: MUST, story: US-005, text: "GDPR erasure: hard-delete content+PII, tombstone remains" }
    REQ-040: { p: MUST, story: US-005, text: "Nightly purge per tenant retention, events logged" }
    REQ-041: { p: MUST, story: US-005, text: "GDPR erasure of in-flight doc: cancel pipeline, purge state, tombstone" }
    REQ-042: { p: MUST, story: US-006, text: "Prometheus metrics at /metrics" }
    REQ-043: { p: MUST, story: US-006, text: "REJECTED/ERROR docs written to DLQ with state snapshot" }
    REQ-044: { p: MUST, story: US-006, text: "DLQ listing paginated, filterable by tenant/status" }
    REQ-045: { p: MUST, story: US-006, text: "DLQ retry re-enters pipeline from start" }
    REQ-046: { p: MUST, story: US-006, text: "LLM circuit breaker: 5 failures/60s, alert within 2min" }
    REQ-047: { p: MUST, story: US-006, text: "Fallback LLM on circuit break; both fail -> DLQ" }
    REQ-048: { p: MUST, story: US-006, text: "Alerts: DLQ>50/5min, breaker OPEN, p95>30s, err>5%" }
    REQ-049: { p: MUST, story: US-006, text: "Webhook exhaustion -> DLQ with last HTTP status" }
    REQ-050: { p: MUST, story: US-006, text: "DLQ retry idempotent (409 on re-retry)" }
    REQ-051: { p: MUST, story: NFR, text: "100 docs/min/tenant, 1000 docs/min platform" }
    REQ-052: { p: MUST, story: NFR, text: "Async workers, configurable concurrency, LangGraph checkpoint to PG" }
    REQ-053: { p: MUST, story: NFR, text: "Structured JSON logs per pipeline step" }
    REQ-054: { p: MUST, story: NFR, text: "Configurable retention per tenant (default 90d)" }
    REQ-055: { p: MUST, story: NFR, text: "Confidence thresholds configurable per schema" }
  nfrs:
    - "100 docs/min/tenant; 1000 docs/min platform-wide"
    - "p95 <15s for 2-page STP"
    - "PostgreSQL RLS on all tenant tables"
    - "Qdrant tenant_id filter enforced at service layer"
    - "AES-256 PII encryption at rest; [REDACTED] in logs"
    - "TLS 1.2+; RS256 JWT"
    - "Append-only audit via PG trigger"
    - "Webhook HMAC-SHA256 signed"
    - "LangGraph state via langgraph-checkpoint-postgres"
  gherkin: [SC-001, SC-002, SC-003, SC-004, SC-005, SC-006, SC-007, SC-008, SC-009, SC-010, SC-011, SC-012, SC-013, SC-014, SC-015, SC-016, SC-017, SC-018, SC-019, SC-020, SC-021, SC-022, SC-023, SC-024, SC-025, SC-026, SC-027, SC-028, SC-029, SC-030, SC-031, SC-032, SC-033, SC-034, SC-035, SC-036, SC-037, SC-038, SC-039, SC-040, SC-041, SC-042, SC-043, SC-044, SC-045, SC-046, SC-047, SC-048, SC-049, SC-050, SC-051]
  edge_cases: [EC-001, EC-002, EC-003, EC-004, EC-005, EC-006, EC-007, EC-008, EC-009, EC-010, EC-011, EC-012, EC-013, EC-014, EC-015, EC-016, EC-017, EC-018]
out_of_scope: [SSO/SAML, embedded PDF viewer, multi-modal vision, data residency, cost optimization, ERP connectors, cross-tenant schema sharing, reviewer assignment routing, bulk-accept, OpenTelemetry tracing, auto prompt generation, duplicate detection]
constraints:
  - "PostgreSQL RLS enforced at DB layer"
  - "Qdrant queries always include tenant_id filter"
  - "LLM prompt never includes cross-tenant data"
  - "Audit table append-only via PG trigger"
  - "PII AES-256 encrypted; masked in logs"
  - "Confidence boundaries: HIGH >=0.85, MEDIUM >=0.60, LOW <0.60 (inclusive upper)"
  - "Webhook retry: 5 attempts exponential backoff (1s,5s,30s,120s,600s)"
  - "GDPR erasure cancels in-flight pipelines"
  - "DLQ retry is idempotent"
  - "Schema activation requires >=3 seed examples"
open:
  - { id: I-001, text: "LLM provider DPA required before PII tenant pilot — GDPR erasure cannot guarantee provider-side log deletion", blocking: true }
  - { id: I-002, text: "Invoice required-field set not confirmed with pilot tenant", blocking: false }
  - { id: I-003, text: "LlamaParse cloud vs self-hosted affects architecture topology", blocking: true }
  - { id: I-004, text: "On-premise deployment changes LLM stack to vLLM", blocking: true }
  - { id: I-005, text: "Guardrail WARN confidence multiplier (0.8x) needs validation", blocking: false }
  - { id: I-006, text: "Correction-to-few-shot immediate write risks RAG pollution", blocking: false }
  - { id: I-007, text: "Per-document pipeline timeout (60s) needs benchmarking", blocking: false }
pull_hint: "full Gherkin scenarios + traceability matrix + edge case table -> 02-requirements.md"
---
