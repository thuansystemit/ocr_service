---
doc: 03-architecture
agent: architect
phase: 2
status: complete
human_doc: 03-architecture.md
source: [01-product-spec, 02-requirements]
next: [data-modeler, api-designer, ux-designer, estimator, engineering]
style: modular-monolith-with-event-driven-internals
provides:
  components:
    - C-01 API Gateway: "JWT RS256 + API key auth, rate limiting, tenant context injection (FastAPI middleware)"
    - C-02 Ingest Module: "File validation, MIME check, enqueue to worker pool, return 202"
    - C-03 Schema Registry: "Schema CRUD, versioning (draft/active/deprecated), seed example mgmt, activation gate (>=3 seeds)"
    - C-04 Review Module: "Review queue CRUD, accept/correct/reject, optimistic locking (version column), stale notification"
    - C-05 Admin Module: "API key lifecycle, DLQ mgmt, audit export (NDJSON/CSV), tenant config, GDPR erasure orchestrator"
    - C-06 Tenant Context: "Propagate tenant_id via contextvars + PG session var (SET LOCAL app.current_tenant_id)"
    - C-07 Audit Service: "Append-only audit_log with SHA-256 hash; PG trigger blocks UPDATE/DELETE"
    - C-08 PII Encryption: "AES-256-GCM field-level enc/dec for pii_fields[]; log masking filter"
    - C-09 Confidence Scorer: "min(llm_self, completeness, semantic) * guardrail_multiplier; configurable thresholds per schema"
    - C-10 LangGraph Pipeline: "Stateful graph: PARSE->GUARDRAIL->EXTRACT->SCORE->ROUTE; checkpoint to PG"
    - C-11 Parse Node: "LlamaParse cloud (default) + pdfplumber/pytesseract fallback; retry 3x"
    - C-12 Guardrail Node: "injection detection, text quality, empty check; WARN (0.8x) or BLOCK (DLQ)"
    - C-13 Extract Node: "Qdrant RAG (tenant-scoped) -> prompt build -> Claude/GPT-4o via LangChain LCEL"
    - C-14 Route Node: "HIGH(>=0.85)->webhook, MEDIUM(>=0.60)->review, LOW(<0.60)->DLQ"
    - C-15 Webhook Delivery: "HMAC-SHA256 sign; retry [1,5,30,120,600]s; DLQ on exhaust"
    - C-16 DLQ: "State snapshot storage; retry endpoint; idempotency guard (409 on re-retry)"
    - C-17 Worker Pool: "asyncio.Semaphore per-tenant concurrency (default 10); HPA in k8s"
    - C-18 Qdrant Service: "Mandatory tenant_id filter; post-query assertion; CRITICAL log on omission"
    - C-19 Circuit Breaker: "5 failures/60s -> OPEN; fallback LLM; alert within 2min"
    - C-20 Metrics Collector: "Prometheus counters/histograms at /metrics"
    - C-21 Notification Service: "24h stale review alert; circuit breaker alerts"
    - C-22 Retention Purge Job: "Nightly cron; delete expired docs + Qdrant vectors; tombstones"
  tables:
    - tenants: "id, name, slug, webhook_url, webhook_secret, max_queue_size, retention_days, pii_to_llm_policy, config"
    - api_keys: "id, tenant_id, key_hash(SHA-256), key_prefix, description, scopes, expires_at, revoked_at"
    - schemas: "id, tenant_id, name, json_schema, required_fields, pii_fields, prompt_template, status, current_version, confidence_high/medium, seed_count"
    - schema_versions: "id, schema_id, tenant_id, version, json_schema, required_fields, pii_fields, prompt_template"
    - documents: "id, tenant_id, schema_id, schema_version, file_name, file_size_bytes, mime_type, file_storage_key, status, confidence_overall, routing_decision, is_dry_run, version(optimistic lock)"
    - extraction_results: "id, document_id, tenant_id, extracted_json(PII encrypted), extracted_json_hash, llm_model_used, llm_token_usage, confidence_overall, confidence_breakdown, low_confidence_fields"
    - guardrail_reports: "id, document_id, tenant_id, guardrail_name, result(pass/warn/block), detail, confidence_multiplier"
    - review_tasks: "id, document_id, tenant_id, extraction_result_id, status, reviewer_id, corrections, rejection_reason, version(optimistic lock)"
    - audit_log: "id, tenant_id, document_id, event_type, actor, status, payload_hash(SHA-256), metadata (APPEND-ONLY via PG trigger)"
    - dlq: "id, document_id, tenant_id, failure_reason, pipeline_state(JSONB), last_http_status, status, retry_count"
    - webhook_deliveries: "id, document_id, tenant_id, attempt, http_status, response_body, error"
  integration:
    - "Client -> C-01 API Gateway (HTTPS/TLS 1.2+)"
    - "C-02 Ingest -> C-17 Worker Pool (async queue)"
    - "C-17 -> C-10 LangGraph Pipeline (async task)"
    - "C-10 -> LlamaParse API (HTTP, with C-11 fallback)"
    - "C-10 -> C-18 Qdrant Service -> Qdrant (HTTP, tenant-filtered)"
    - "C-10 -> Claude API / GPT-4o API (HTTP, via C-19 circuit breaker)"
    - "C-14 Route -> C-15 Webhook (HIGH) | C-04 Review (MEDIUM) | C-16 DLQ (LOW/ERROR)"
    - "C-04 Review accept -> C-15 Webhook + C-18 Qdrant (few-shot write)"
    - "All modules -> C-07 Audit Service (sync function call)"
    - "C-22 Purge Job -> PG + Qdrant (SQL + HTTP, nightly cron)"
  qdrant:
    collection: "ocr_few_shot (single collection)"
    payload: "tenant_id, schema_id, document_id, schema_name, source(seed|correction), input_text, expected_json"
    isolation: "mandatory tenant_id filter + post-query assertion"
decisions:
  D-001: "Modular monolith (affects: all modules; extract to microservices at >10 engineers)"
  D-002: "LangGraph + PG checkpoint (affects: pipeline, crash recovery EC-012)"
  D-003: "Shared PG schema + RLS (affects: all tables, tenant context middleware)"
  D-004: "Single Qdrant collection + payload filter (affects: C-18, RAG queries)"
  D-005: "API key SHA-256 hash (affects: api_keys table, auth middleware)"
  D-006: "Confidence = min(llm,completeness,semantic)*guardrail_mult (affects: C-09, routing)"
  D-007: "Configurable pii_to_llm_policy per tenant (affects: C-08, C-13, DPA compliance)"
  D-008: "Webhook retry [1,5,30,120,600]s fixed (affects: C-15)"
  D-009: "Per-process circuit breaker (affects: C-19, no shared state)"
  D-010: "AES-256-GCM field-level PII encryption (affects: extraction_results, C-08)"
  D-011: "PG trigger audit immutability (affects: audit_log, GDPR erasure procedure)"
  D-012: "asyncio.Semaphore worker pool (affects: C-17, concurrency control)"
constraints:
  - "auth: JWT RS256 + API key (SHA-256 hashed); tenant_id from JWT claim or api_keys lookup"
  - "db PK: UUID (gen_random_uuid())"
  - "base package: app/"
  - "framework: FastAPI + Uvicorn (async)"
  - "ORM: SQLAlchemy 2.0 async"
  - "migrations: Alembic"
  - "RLS: SET LOCAL app.current_tenant_id on every connection"
  - "Qdrant: mandatory tenant_id filter, post-query assertion"
  - "LLM: LangChain BaseChatModel abstraction; primary Claude claude-sonnet-4-6, fallback GPT-4o"
  - "pipeline: LangGraph with langgraph-checkpoint-postgres; thread_id = document_id"
  - "confidence: HIGH>=0.85, MEDIUM>=0.60, LOW<0.60 (inclusive upper tier)"
  - "PII: AES-256-GCM field-level; [REDACTED] in logs"
  - "audit: append-only PG trigger; SHA-256 payload hash"
  - "webhook: HMAC-SHA256 signed; retry [1,5,30,120,600]s"
  - "GDPR erasure: cancel in-flight, purge checkpoint+content+vectors, tombstone"
  - "worker: asyncio.Semaphore per-tenant (default 10)"
  - "deployment: Docker Compose (dev), Kubernetes (prod)"
  - "observability: Prometheus metrics at /metrics; structured JSON logs"
langgraph:
  state: "ExtractionState TypedDict with document_id, tenant_id, schema_id, schema_version, status, raw_text, guardrail_results, extracted_json, confidence, routing_decision, error, is_cancelled"
  nodes: [PARSE, GUARDRAIL, EXTRACT, SCORE, ROUTE, WEBHOOK, CREATE_REVIEW, DLQ_WRITE, COMPLETE]
  checkpoint: "langgraph-checkpoint-postgres; thread_id=document_id; resume from last completed node"
  cancellation: "is_cancelled flag checked between nodes for GDPR erasure"
open:
  - "I-001: LLM provider DPA (legal, not arch) -- arch addressed via pii_to_llm_policy"
  - "I-005: Guardrail WARN multiplier 0.8x needs validation (configurable)"
  - "I-006: Correction-to-few-shot immediate write risk (Phase 2 gate)"
  - "I-007: Pipeline timeout 60s default needs benchmarking (configurable)"
pull_hint: "component diagram, full PG schema DDL, LangGraph workflow diagram, confidence algorithm, RLS policies, Qdrant guard, deployment topology, ADR list -> 03-architecture.md"
---
