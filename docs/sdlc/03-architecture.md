# Architecture -- Enterprise OCR / Document Extraction Platform
**Date:** 2026-06-09  **Author:** @architect  **Status:** DECIDED
**Sources:** `docs/sdlc/01-product-spec.md`, `docs/sdlc/02-requirements.md`

---

## 1. Requirement & Context Summary

### 1.1 Functional Requirements (55 total, all MUST)

The system must provide:
- REST API ingest (`POST /api/v1/extract`) returning 202 within 500ms (REQ-001)
- End-to-end STP pipeline (LlamaParse -> guardrails -> LLM extraction -> confidence routing -> webhook) completing in <15s p95 for 2-page PDF (REQ-002)
- Three-tier confidence routing: HIGH (>=0.85) -> webhook, MEDIUM (0.60..0.84) -> review queue, LOW (<0.60) -> DLQ (REQ-003/009/010)
- Human-in-the-loop review with optimistic locking, corrections persisted to Qdrant as few-shot examples (REQ-014..020)
- Self-service schema registry with draft/active lifecycle, seed example indexing, dry-run extraction (REQ-021..027)
- Multi-tenant isolation via PostgreSQL RLS + Qdrant tenant filter + JWT RS256 (REQ-028..035)
- Immutable append-only audit trail with GDPR erasure and nightly purge (REQ-036..041)
- DLQ management, LLM circuit breaker with fallback, Prometheus metrics (REQ-042..050)
- Platform throughput: 100 docs/min/tenant, 1000 docs/min platform (REQ-051)

### 1.2 Non-Functional Requirements

| NFR | Requirement | Priority | Source |
|-----|------------|----------|--------|
| Latency | p95 <15s STP for 2-page PDF; API 202 <500ms | P0 | REQ-001, REQ-002 |
| Throughput | 100 docs/min/tenant; 1000 docs/min platform | P0 | REQ-051 |
| Isolation | PostgreSQL RLS + Qdrant tenant filter + JWT | P0 | REQ-028..035 |
| Encryption | AES-256 PII at rest; TLS 1.2+ in transit | P0 | REQ-031, REQ-034 |
| Audit | Append-only PG trigger; SHA-256 payload hash | P0 | REQ-036, REQ-037 |
| Availability | Circuit breaker + LLM fallback; webhook retry 5x | P0 | REQ-046, REQ-047 |
| Observability | Prometheus metrics; structured JSON logs | P0 | REQ-042, REQ-053 |
| GDPR | Erasure of at-rest and in-flight docs; tombstone | P0 | REQ-039, REQ-041 |

### 1.3 System Boundaries

```
IN SCOPE (this system):
  - REST API for document ingest, schema management, review, admin, audit
  - Document parsing pipeline (LlamaParse integration)
  - LLM-based structured extraction (Claude primary, GPT-4o fallback)
  - Few-shot RAG retrieval via Qdrant
  - Confidence scoring and routing
  - Human review queue
  - Webhook delivery with retry
  - DLQ management
  - Multi-tenant data isolation
  - Audit trail and GDPR compliance

OUT OF SCOPE:
  - SSO/SAML (Phase 3)
  - Embedded PDF viewer (Phase 2)
  - Multi-modal vision path (Phase 2)
  - Data residency per-tenant (Phase 3)
  - ERP/SAP connectors
  - Cross-tenant schema sharing
  - OpenTelemetry distributed tracing (Phase 2; Prometheus + structured logs at MVP)
```

### 1.4 Stakeholders

| Stakeholder | Key concern |
|------------|------------|
| Ops Analyst | Accurate extraction, zero re-keying |
| Document Engineer | Fast schema onboarding, prompt iteration |
| Tenant Admin | Isolation, API keys, SLA monitoring |
| Platform Operator | Observability, scaling, cost, LLM uptime |
| Compliance Officer | Immutable audit trail, GDPR erasure, PII handling |

### 1.5 Assumptions & Constraints

| ID | Assumption / Constraint |
|----|------------------------|
| A-01 | Cloud LlamaParse API at MVP (recommended default; see I-003 resolution below) |
| A-02 | Cloud LLMs (Claude, GPT-4o) at MVP (recommended default; see I-004 resolution below) |
| A-03 | Single-region deployment at MVP |
| A-04 | No Redis at MVP -- LangGraph state via langgraph-checkpoint-postgres |
| A-05 | Peak load will not exceed 1000 docs/min platform-wide in year 1 |
| C-01 | Tech stack fixed: FastAPI, LangChain, LangGraph, LlamaParse, Qdrant, PostgreSQL 16 |
| C-02 | PostgreSQL RLS enforced at DB layer, not app-only |
| C-03 | Qdrant queries always include tenant_id filter at service layer |
| C-04 | LLM prompt never includes cross-tenant data |
| C-05 | Audit table append-only via PG trigger |
| C-06 | PII AES-256 encrypted at rest; [REDACTED] in all logs |
| C-07 | Confidence boundaries: HIGH >=0.85, MEDIUM >=0.60, LOW <0.60 |

### 1.6 Blocking Open Issues -- Resolution

| Issue | Resolution | Rationale |
|-------|-----------|-----------|
| I-001 (LLM provider DPA) | **Architecture designs for cloud LLMs as default. DPA is a legal/procurement blocker, not an architecture blocker.** The system includes a PII encryption layer that encrypts PII fields before they reach the LLM prompt (D-010). If DPA is not signed before pilot, the platform can operate with PII fields redacted from LLM input (degraded accuracy) or tenants must not submit PII documents. Architecture supports both modes via a `pii_to_llm_policy` tenant config: `ENCRYPT_BEFORE_LLM` (default), `REDACT_BEFORE_LLM`, `ALLOW_PLAINTEXT` (requires DPA). |
| I-003 (LlamaParse cloud vs self-hosted) | **Architecture defaults to cloud LlamaParse API. Self-hosted is a deployment-time configuration swap.** The parsing layer abstracts behind a `DocumentParser` interface. Cloud LlamaParse and local fallback (pdfplumber+pytesseract) are both implementations. Self-hosted LlamaParse (when available) plugs into the same interface. No architecture change required. |
| I-004 (On-prem deployment) | **Architecture defaults to cloud LLMs (Claude + GPT-4o). On-prem swaps to vLLM behind the same LangChain interface.** The LLM integration uses LangChain's `BaseChatModel` abstraction. Switching to vLLM requires: (1) deploy vLLM container, (2) set `LLM_PROVIDER=vllm` + `LLM_BASE_URL` in config. The circuit breaker and fallback logic remain identical. Docker Compose and Kubernetes manifests include commented vLLM service definition. |

---

## 2. Architecture Design

### 2.1 Selected Architecture Style

**Style:** Modular Monolith with Event-Driven Internals

**Rationale:**
- Team size is small (startup/early product); microservices add premature operational complexity
- Domain boundaries are clear but coupled (ingest -> parse -> extract -> route -> deliver -- a single pipeline)
- The LangGraph workflow is inherently a single-process stateful graph -- splitting it across services adds latency and complexity with no benefit
- All state lives in PostgreSQL (single DB) which simplifies transactions, RLS, and checkpoint recovery
- Async workers provide horizontal scaling without service decomposition
- NFR throughput (1000 docs/min) is achievable with async workers on a monolith

**Trade-offs accepted:**
- Cannot independently scale parse vs LLM vs webhook delivery (mitigated by worker pool partitioning)
- Single deployment unit means all components share a release cycle (acceptable at MVP scale)
- If platform grows past ~10 engineers or ~5000 docs/min, extract parsing and webhook delivery into separate services

**Internal layering:** Clean/Hexagonal within the monolith -- each domain module has clear boundaries, communicates via internal events (Python async queues at MVP), and owns its own repository layer. This makes future service extraction straightforward.

### 2.2 Component Architecture

```
                            EXTERNAL CLIENTS
                                  |
                            TLS 1.2+ / HTTPS
                                  |
                    +-------------v--------------+
                    |        API Gateway          |
                    |  (FastAPI + Uvicorn)         |
                    |  - JWT RS256 validation      |
                    |  - API key auth              |
                    |  - Rate limiting (429)        |
                    |  - Request validation         |
                    |  - Tenant context injection   |
                    +----+----+----+----+----+-----+
                         |    |    |    |    |
          +--------------+    |    |    |    +------------------+
          |                   |    |    |                       |
    +-----v------+   +-------v-+  | +--v--------+   +---------v--------+
    | Ingest     |   | Schema  |  | | Review    |   | Admin            |
    | Module     |   | Registry|  | | Module    |   | Module           |
    | - file val |   | - CRUD  |  | | - queue   |   | - API keys       |
    | - mime chk |   | - ver-  |  | | - accept  |   | - DLQ mgmt       |
    | - enqueue  |   |   sion  |  | | - correct |   | - audit export   |
    | - 202 resp |   | - seed  |  | | - reject  |   | - tenant config  |
    +-----+------+   | - activ |  | | - lock    |   | - GDPR erasure   |
          |          +----+----+  | +--+--------+   +--------+---------+
          |               |       |    |                      |
          +-------+-------+-------+----+----------------------+
                  |                                           |
          +-------v-------------------------------------------v--------+
          |                    DOMAIN CORE                              |
          |                                                            |
          |  +------------------+    +---------------------+           |
          |  | Tenant Context   |    | Audit Service       |           |
          |  | - propagation    |    | - append-only write  |           |
          |  | - RLS session    |    | - SHA-256 hashing    |           |
          |  +------------------+    +---------------------+           |
          |                                                            |
          |  +------------------+    +---------------------+           |
          |  | PII Encryption   |    | Confidence Scorer   |           |
          |  | - AES-256 enc    |    | - LLM self-report   |           |
          |  | - field masking  |    | - completeness       |           |
          |  | - log redaction  |    | - semantic valid.    |           |
          |  +------------------+    | - threshold routing  |           |
          |                          +---------------------+           |
          +------------------------------------------------------------+
                  |
          +-------v------------------------------------------------+
          |              EXTRACTION PIPELINE (LangGraph)            |
          |                                                        |
          |  +----------+  +----------+  +-----------+  +--------+ |
          |  | Parse    |  | Guardrail|  | Extract   |  | Route  | |
          |  | Node     |  | Node     |  | Node      |  | Node   | |
          |  | LlamaPrse|  | inject.  |  | Claude/   |  | HIGH/  | |
          |  | +fallback|  | text_qual|  | GPT-4o    |  | MED/   | |
          |  |          |  | file_sz  |  | + Qdrant  |  | LOW    | |
          |  +----+-----+  +----+-----+  | RAG       |  +---+----+ |
          |       |             |         +----+------+      |      |
          |       +------+------+------+-------+------+------+      |
          |              |                                          |
          |       +------v-------+                                  |
          |       | State Object |  (LangGraph checkpoint -> PG)   |
          |       +--------------+                                  |
          +---+-------------------------------------------+--------+
              |                                           |
     +--------v---------+                        +--------v---------+
     | Webhook Delivery  |                        | Review Queue     |
     | - HMAC-SHA256 sign|                        | Writer           |
     | - retry 5x exp    |                        | - create item    |
     | - DLQ on exhaust  |                        | - 24h stale notif|
     +--------+----------+                        +------------------+
              |
     +--------v---------+
     | DLQ               |
     | - state snapshot   |
     | - retry endpoint   |
     | - idempotency      |
     +-------------------+

              INFRASTRUCTURE LAYER
     +---------------------------------------------------+
     |  PostgreSQL 16          Qdrant         Prometheus  |
     |  - tenant data (RLS)   - per-tenant   - /metrics  |
     |  - audit_log           - seed vectors  - Grafana   |
     |  - langgraph chkpt     - few-shot RAG              |
     |  - schema registry                                 |
     |  - DLQ table                                       |
     +---------------------------------------------------+
```

### 2.3 Component Registry

| # | Component | Responsibility | Technology | New/Existing |
|---|-----------|---------------|-----------|-------------|
| C-01 | API Gateway | JWT/API-key auth, rate limiting, tenant context, request routing | FastAPI + Uvicorn | New |
| C-02 | Ingest Module | File validation (type, size), MIME check, enqueue to worker pool, return 202 | FastAPI router + Pydantic | New |
| C-03 | Schema Registry Module | Schema CRUD, versioning, seed example management, activation gate | FastAPI router + SQLAlchemy | New |
| C-04 | Review Module | Review queue CRUD, field editing, accept/correct/reject, optimistic locking | FastAPI router + SQLAlchemy | New |
| C-05 | Admin Module | API key lifecycle, DLQ management, audit export, tenant config, GDPR erasure | FastAPI router + SQLAlchemy | New |
| C-06 | Tenant Context | Propagate tenant_id through request lifecycle; set PostgreSQL RLS session var | Middleware + contextvars | New |
| C-07 | Audit Service | Append audit records with SHA-256 hash; never update/delete | SQLAlchemy + PG trigger | New |
| C-08 | PII Encryption Service | AES-256 field-level encryption/decryption; log masking filter | cryptography lib + logging filter | New |
| C-09 | Confidence Scorer | Compute overall confidence from LLM self-report, completeness, semantic scores; apply guardrail multiplier; route by threshold | Pure Python | New |
| C-10 | LangGraph Extraction Pipeline | Stateful workflow: parse -> guardrail -> extract -> route; checkpoint to PG | LangGraph + langgraph-checkpoint-postgres | New |
| C-11 | Parse Node | Call LlamaParse API; fallback to pdfplumber+pytesseract; retry 3x | LlamaParse SDK + pdfplumber | New |
| C-12 | Guardrail Node | Prompt injection detection, text quality check, file size re-check; WARN/BLOCK | Custom guardrails (reuse cv-batch-extractor patterns) | New |
| C-13 | Extract Node | Build prompt with schema + Qdrant few-shot examples; call LLM; parse response | LangChain LCEL + Qdrant client | New |
| C-14 | Route Node | Apply confidence thresholds; route to webhook/review/DLQ | Pure Python | New |
| C-15 | Webhook Delivery | HMAC-SHA256 sign payload; deliver with 5x exponential backoff; DLQ on exhaust | httpx + asyncio | New |
| C-16 | DLQ | Store failed docs with state snapshot; retry endpoint; idempotency guard | SQLAlchemy + FastAPI router | New |
| C-17 | Worker Pool | Async task execution; configurable concurrency per tenant; queue depth tracking | asyncio.Semaphore + background tasks | New |
| C-18 | Qdrant Service | Tenant-scoped vector operations; hard reject on missing tenant_id | qdrant-client + service guard | New |
| C-19 | Circuit Breaker | Track LLM failures; OPEN after 5/60s; route to fallback; alert on state change | Custom (aiobreaker pattern) | New |
| C-20 | Metrics Collector | Prometheus counters/histograms; /metrics endpoint | prometheus-client | New |
| C-21 | Notification Service | 24h stale review alert; circuit breaker alerts | Configurable (email/Slack webhook) | New |
| C-22 | Retention Purge Job | Nightly cron; delete expired docs + Qdrant vectors; audit tombstones | APScheduler or cron | New |

### 2.4 Data Ownership

| Component | Owns (tables) | Must NOT access |
|-----------|--------------|----------------|
| Ingest Module | documents (create only) | schemas (reads via Schema Registry) |
| Schema Registry | schemas, schema_versions, seed_examples | documents, extraction_results |
| Review Module | review_tasks (CRUD) | schemas, api_keys |
| Admin Module | api_keys, tenant_config | extraction_results (reads via service) |
| Audit Service | audit_log (append only) | all other tables (receives events) |
| DLQ | dlq (CRUD) | schemas, api_keys |
| Extraction Pipeline | extraction_results, guardrail_reports | api_keys, review_tasks |
| Webhook Delivery | webhook_deliveries | schemas, api_keys |

Note: Because this is a modular monolith sharing a single PostgreSQL database, "ownership" means the module is the only code path that writes to these tables. Other modules read via well-defined service interfaces. PostgreSQL RLS provides the hard tenant boundary regardless of which module issues the query.

### 2.5 Integration Map

| From | To | Pattern | Trigger / Reason |
|------|----|---------|-----------------|
| API Gateway | Ingest Module | Sync (function call) | POST /api/v1/extract |
| Ingest Module | Worker Pool | Async (queue) | Enqueue document for pipeline |
| Worker Pool | LangGraph Pipeline | Async (task) | Execute extraction workflow |
| LangGraph Pipeline | LlamaParse API | HTTP (external) | Document parsing |
| LangGraph Pipeline | Qdrant | HTTP (external) | Few-shot RAG retrieval |
| LangGraph Pipeline | Claude API | HTTP (external) | LLM extraction |
| LangGraph Pipeline | GPT-4o API | HTTP (external, fallback) | LLM fallback on circuit break |
| Route Node | Webhook Delivery | Async (internal event) | HIGH confidence result |
| Route Node | Review Queue Writer | Async (internal event) | MEDIUM confidence result |
| Route Node | DLQ | Async (internal event) | LOW confidence / errors |
| Webhook Delivery | Tenant webhook URL | HTTP (external) | Deliver extraction result |
| Webhook Delivery | DLQ | Sync (write) | Retry exhaustion |
| Review Module | Webhook Delivery | Async (internal event) | Accept/correct triggers webhook |
| Review Module | Qdrant Service | HTTP (external) | Write corrected few-shot example |
| All Modules | Audit Service | Sync (function call) | Every state change event |
| Admin Module | LangGraph checkpoint | SQL (direct) | GDPR in-flight erasure |
| Retention Purge Job | PostgreSQL + Qdrant | SQL + HTTP | Nightly cleanup |

---

## 3. LangGraph Extraction Pipeline

### 3.1 Workflow Graph

```
                    +------------------+
                    |   START          |
                    |   (document_id,  |
                    |    tenant_id,    |
                    |    schema_id,    |
                    |    schema_ver)   |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  PARSE           |
                    |  - LlamaParse    |
                    |  - fallback:     |
                    |    pdfplumber    |
                    |  - retry 3x     |
                    +--------+---------+
                             |
                    success?-+--fail--> DLQ_SINK (PARSE_FAILED)
                             |
                    +--------v---------+
                    |  GUARDRAIL       |
                    |  - injection det |
                    |  - text quality  |
                    |  - empty check   |
                    +--------+---------+
                             |
                    result?--+--BLOCK--> DLQ_SINK (GUARDRAIL_BLOCK / INJECTION / PARSE_EMPTY)
                             |
                          PASS/WARN
                             |
                    +--------v---------+
                    |  EXTRACT         |
                    |  - load schema   |
                    |  - Qdrant RAG    |
                    |    (tenant-      |
                    |     scoped)      |
                    |  - build prompt  |
                    |  - call LLM      |
                    |    (circuit      |
                    |     breaker)     |
                    |  - parse JSON    |
                    +--------+---------+
                             |
                    success?-+--fail--> DLQ_SINK (LLM_UNAVAILABLE / EXTRACTION_FAILED)
                             |
                    +--------v---------+
                    |  SCORE           |
                    |  - LLM self-conf |
                    |  - completeness  |
                    |  - semantic val  |
                    |  - guardrail     |
                    |    multiplier    |
                    |  - overall score |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  ROUTE           |
                    |  conf >= 0.85?   +----YES----> DELIVER (status=PASS)
                    |  conf >= 0.60?   +----YES----> REVIEW_QUEUE (status=DEGRADED)
                    |  conf < 0.60?    +----YES----> DLQ_SINK (status=REJECTED, LOW_CONFIDENCE)
                    +------------------+

                    DELIVER:
                    +------------------+
                    |  WEBHOOK         |
                    |  - HMAC sign     |
                    |  - POST to URL   |
                    |  - retry 5x      |
                    +--------+---------+
                             |
                    exhaust?-+--fail--> DLQ_SINK (WEBHOOK_DELIVERY_FAILED)
                             |
                    +--------v---------+
                    |  COMPLETE        |
                    |  - mark DONE     |
                    |  - audit record  |
                    +------------------+

                    REVIEW_QUEUE:
                    +------------------+
                    |  CREATE_REVIEW   |
                    |  - insert task   |
                    |  - fire webhook  |
                    |    (DEGRADED)    |
                    +------------------+

                    DLQ_SINK:
                    +------------------+
                    |  DLQ_WRITE       |
                    |  - save state    |
                    |  - fire webhook  |
                    |    (REJECTED/ERR)|
                    |  - audit record  |
                    +------------------+
```

### 3.2 State Object

```python
from typing import TypedDict, Optional, Any
from datetime import datetime
from enum import Enum

class PipelineStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    GUARDING = "guarding"
    EXTRACTING = "extracting"
    SCORING = "scoring"
    ROUTING = "routing"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    REVIEW = "review"
    DLQ = "dlq"
    CANCELLED = "cancelled"  # GDPR erasure

class GuardrailResult(str, Enum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"

class ExtractionState(TypedDict):
    # Identity (immutable after START)
    document_id: str           # UUID
    tenant_id: str             # UUID
    schema_id: str             # UUID
    schema_version: int        # pinned at submission time

    # Pipeline progress
    status: PipelineStatus
    current_step: str          # node name for checkpoint recovery
    started_at: datetime
    updated_at: datetime

    # Parse output
    raw_text: Optional[str]
    parse_method: Optional[str]         # "llamaparse" | "pdfplumber" | "pytesseract"
    parse_retries: int

    # Guardrail output
    guardrail_results: list[dict]       # [{name, result, detail}]
    guardrail_overall: Optional[GuardrailResult]
    guardrail_confidence_multiplier: float  # 1.0 for PASS, 0.8 for WARN

    # Extraction output
    extracted_json: Optional[dict[str, Any]]
    llm_model_used: Optional[str]
    llm_token_usage: Optional[dict]     # {prompt_tokens, completion_tokens}
    llm_self_confidence: Optional[float]
    extraction_retries: int

    # Scoring output
    confidence_overall: Optional[float]
    confidence_breakdown: Optional[dict]  # {llm, completeness, semantic, guardrail_adjusted}
    low_confidence_fields: list[str]
    routing_decision: Optional[str]       # "HIGH" | "MEDIUM" | "LOW"

    # Delivery
    webhook_attempts: int
    webhook_last_status: Optional[int]

    # Error tracking
    error: Optional[str]
    failure_reason: Optional[str]

    # Flags
    dry_run: bool
    is_cancelled: bool         # set by GDPR erasure
```

### 3.3 Checkpoint & Recovery Semantics (EC-012)

**Checkpoint strategy:** LangGraph with `langgraph-checkpoint-postgres` checkpoints state after every node completes. Each node is an atomic unit.

**Recovery on crash:**
1. Worker restarts and queries the checkpoint table for incomplete documents (status not in COMPLETED, DLQ, CANCELLED).
2. For each incomplete document, the last checkpointed state is loaded.
3. The pipeline resumes from `current_step` -- the next node after the last completed one.
4. Because each node is idempotent or checkpointed at completion, no LLM call is duplicated.

**Idempotency per node:**
- PARSE: re-parse is safe (deterministic). If already parsed (`raw_text` is set), skip.
- GUARDRAIL: re-run is safe (deterministic, no side effects).
- EXTRACT: check if `extracted_json` is already set. If yes, skip LLM call. This prevents duplicate LLM costs.
- SCORE: re-compute is safe (pure function).
- ROUTE: check if `routing_decision` is set. If yes, skip (prevents duplicate review items or DLQ entries).
- WEBHOOK: check `webhook_attempts` counter. If delivery succeeded (status 2xx recorded), skip.

**GDPR erasure of in-flight documents (EC-005/EC-018, REQ-041):**
1. `DELETE /api/v1/documents/{id}` sets `is_cancelled = true` in the checkpoint state.
2. A cancellation signal is sent to the worker (via a shared cancellation registry keyed by document_id).
3. The active pipeline node checks `is_cancelled` before proceeding to the next node. If true, the pipeline transitions to CANCELLED status.
4. All document content, PII, raw_text, and extracted_json are hard-deleted from PostgreSQL.
5. The LangGraph checkpoint row for this document is deleted.
6. Qdrant vectors for this document (if any few-shot examples were written) are deleted.
7. A tombstone audit record is written with `event_type: ERASURE_IN_FLIGHT`.

**Race condition (EC-018): GDPR erasure vs DLQ retry:**
- Erasure sets a tombstone flag in the documents table.
- Before any pipeline step, the worker checks for the tombstone. If present, the pipeline aborts.
- DLQ retry checks for tombstone before re-entering. If tombstoned, returns 410 Gone.

### 3.4 Timeout Handling (SC-051, I-007)

- Per-document timeout: default 60s, configurable per schema.
- Implemented via `asyncio.wait_for()` wrapping the LangGraph execution.
- On timeout: pipeline is cancelled, partial state preserved in DLQ record with `failure_reason: PIPELINE_TIMEOUT`, webhook fires with status ERROR.

---

## 4. Data Architecture

### 4.1 PostgreSQL Schema

#### Core Tables

```sql
-- Tenants
CREATE TABLE tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(63) NOT NULL UNIQUE,
    webhook_url     TEXT,
    webhook_secret  TEXT NOT NULL,           -- for HMAC-SHA256 signing
    max_queue_size  INT NOT NULL DEFAULT 500,
    retention_days  INT NOT NULL DEFAULT 90,
    pii_to_llm_policy VARCHAR(30) NOT NULL DEFAULT 'ENCRYPT_BEFORE_LLM',
    config          JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- API Keys
CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    key_hash        VARCHAR(128) NOT NULL,  -- SHA-256 of the API key
    key_prefix      VARCHAR(8) NOT NULL,    -- first 8 chars for identification
    description     TEXT,
    scopes          TEXT[] NOT NULL DEFAULT '{"extract","read"}',
    expires_at      TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_tenant_id ON api_keys(tenant_id);

-- Schemas (document types)
CREATE TABLE schemas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    json_schema     JSONB NOT NULL,
    required_fields TEXT[] NOT NULL DEFAULT '{}',
    pii_fields      TEXT[] NOT NULL DEFAULT '{}',
    prompt_template TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'draft',  -- draft | active | deprecated
    current_version INT NOT NULL DEFAULT 1,
    confidence_high FLOAT NOT NULL DEFAULT 0.85,
    confidence_medium FLOAT NOT NULL DEFAULT 0.60,
    seed_count      INT NOT NULL DEFAULT 0,
    config          JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, name)
);
CREATE INDEX idx_schemas_tenant_id ON schemas(tenant_id);

-- Schema Versions (immutable snapshots)
CREATE TABLE schema_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schema_id       UUID NOT NULL REFERENCES schemas(id),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    version         INT NOT NULL,
    json_schema     JSONB NOT NULL,
    required_fields TEXT[] NOT NULL,
    pii_fields      TEXT[] NOT NULL,
    prompt_template TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(schema_id, version)
);

-- Documents
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    schema_id       UUID NOT NULL REFERENCES schemas(id),
    schema_version  INT NOT NULL,
    file_name       VARCHAR(512),
    file_size_bytes BIGINT,
    mime_type       VARCHAR(100),
    file_storage_key TEXT,              -- S3/local path to uploaded file
    status          VARCHAR(30) NOT NULL DEFAULT 'pending',
    -- pending | parsing | extracting | completed | review | rejected | error | cancelled | tombstone
    confidence_overall FLOAT,
    routing_decision VARCHAR(10),       -- HIGH | MEDIUM | LOW
    is_dry_run      BOOLEAN NOT NULL DEFAULT false,
    pipeline_timeout_s INT NOT NULL DEFAULT 60,
    version         INT NOT NULL DEFAULT 1,  -- optimistic locking
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_documents_tenant_id ON documents(tenant_id);
CREATE INDEX idx_documents_status ON documents(tenant_id, status);
CREATE INDEX idx_documents_created_at ON documents(tenant_id, created_at);

-- Extraction Results
CREATE TABLE extraction_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    extracted_json  JSONB,                  -- PII fields AES-256 encrypted within
    extracted_json_hash VARCHAR(64),        -- SHA-256 of extracted_json
    llm_model_used  VARCHAR(100),
    llm_token_usage JSONB,
    confidence_overall FLOAT,
    confidence_breakdown JSONB,             -- {llm, completeness, semantic, guardrail}
    low_confidence_fields TEXT[],
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_extraction_results_document_id ON extraction_results(document_id);
CREATE INDEX idx_extraction_results_tenant_id ON extraction_results(tenant_id);

-- Guardrail Reports
CREATE TABLE guardrail_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    guardrail_name  VARCHAR(100) NOT NULL,
    result          VARCHAR(10) NOT NULL,   -- pass | warn | block
    detail          TEXT,
    confidence_multiplier FLOAT NOT NULL DEFAULT 1.0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_guardrail_reports_document_id ON guardrail_reports(document_id);

-- Review Tasks
CREATE TABLE review_tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    extraction_result_id UUID NOT NULL REFERENCES extraction_results(id),
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending | in_progress | accepted | corrected | rejected
    assigned_to     UUID,                   -- user_id, nullable at MVP
    reviewer_id     UUID,                   -- who acted
    corrections     JSONB,                  -- {field: {old, new}}
    rejection_reason TEXT,
    version         INT NOT NULL DEFAULT 1,  -- optimistic locking
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_review_tasks_tenant_id_status ON review_tasks(tenant_id, status);
CREATE INDEX idx_review_tasks_created_at ON review_tasks(created_at);

-- Audit Log (append-only)
CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    document_id     UUID,
    event_type      VARCHAR(50) NOT NULL,
    actor           VARCHAR(255),          -- user_id, system, api_key_prefix
    status          VARCHAR(30),
    payload_hash    VARCHAR(64),           -- SHA-256
    metadata        JSONB,                 -- non-PII context
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_log_tenant_id ON audit_log(tenant_id);
CREATE INDEX idx_audit_log_document_id ON audit_log(document_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(tenant_id, created_at);

-- Audit log immutability trigger
CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit log records cannot be modified or deleted';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_no_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

CREATE TRIGGER trg_audit_no_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW
    WHEN (OLD.event_type NOT IN ('ERASURE_AT_REST', 'ERASURE_IN_FLIGHT', 'RETENTION_PURGE'))
    EXECUTE FUNCTION prevent_audit_modification();
-- Note: tombstone records bypass the delete trigger because they ARE the erasure evidence.
-- The tombstone INSERT (with event_type ERASURE_*) is the last step; the original content
-- records are deleted via a privileged connection that temporarily disables the trigger
-- for that specific transaction, documented in the erasure runbook.

-- Dead Letter Queue
CREATE TABLE dlq (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    failure_reason  VARCHAR(100) NOT NULL,
    pipeline_state  JSONB,                  -- snapshot of ExtractionState
    last_http_status INT,                   -- for webhook failures
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending | retrying | resolved | expired
    retry_count     INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_dlq_tenant_id_status ON dlq(tenant_id, status);

-- Webhook Deliveries (tracking)
CREATE TABLE webhook_deliveries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    attempt         INT NOT NULL,
    http_status     INT,
    response_body   TEXT,                   -- truncated, first 1KB
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_webhook_deliveries_document_id ON webhook_deliveries(document_id);

-- LangGraph Checkpoints (managed by langgraph-checkpoint-postgres)
-- Table created automatically by the library; schema:
-- checkpoints(thread_id, checkpoint_id, parent_id, checkpoint, metadata, created_at)
-- We set thread_id = document_id for 1:1 mapping.
```

#### GDPR Erasure Implementation

```sql
-- Erasure procedure (called by Admin Module)
-- Uses a privileged connection that can bypass audit trigger temporarily

-- Step 1: Cancel in-flight pipeline (application layer sets is_cancelled)
-- Step 2: Delete content
--   DELETE extracted_json, file_storage_key, raw content from documents
--   DELETE extraction_results WHERE document_id = ?
--   DELETE guardrail_reports WHERE document_id = ?
--   DELETE review_tasks WHERE document_id = ?
--   DELETE FROM checkpoints WHERE thread_id = ? (LangGraph state)
-- Step 3: Delete Qdrant vectors for document
-- Step 4: Update document status to 'tombstone'
-- Step 5: Insert tombstone audit record
--   INSERT INTO audit_log (event_type='ERASURE_AT_REST' or 'ERASURE_IN_FLIGHT', ...)
```

### 4.2 Row-Level Security (Multi-Tenancy)

```sql
-- Enable RLS on all tenant-scoped tables
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE extraction_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE guardrail_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE schemas ENABLE ROW LEVEL SECURITY;
ALTER TABLE schema_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE dlq ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_deliveries ENABLE ROW LEVEL SECURITY;

-- RLS policy: tenant can only see own rows
-- Uses session variable set by application middleware
CREATE POLICY tenant_isolation ON documents
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

CREATE POLICY tenant_isolation ON extraction_results
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- (same pattern for all tenant-scoped tables)

-- Application sets session variable on every request:
--   SET LOCAL app.current_tenant_id = '<tenant_uuid>';
-- This is done in the Tenant Context middleware after JWT validation.

-- IMPORTANT: The worker pool connection also sets this variable before
-- processing each document, ensuring RLS applies to background tasks too.

-- Superuser/admin operations (GDPR erasure, nightly purge) use a
-- separate connection role that bypasses RLS:
CREATE ROLE ocr_admin NOLOGIN;
GRANT ALL ON ALL TABLES IN SCHEMA public TO ocr_admin;
ALTER TABLE documents FORCE ROW LEVEL SECURITY; -- even owner must comply
-- ocr_admin bypasses via: ALTER ROLE ocr_admin BYPASSRLS;
-- This role is used ONLY for erasure and purge, never for API requests.
```

### 4.3 Qdrant Collection & Namespace Strategy

```
QDRANT DESIGN

Collection: "ocr_few_shot"  (single collection, tenant-isolated via payload filter)

Vector dimension: 1536 (text-embedding-3-small) or 768 (configurable)
Distance metric: Cosine

Point payload schema:
{
    "tenant_id":    "<uuid>",      -- MANDATORY filter field
    "schema_id":    "<uuid>",
    "document_id":  "<uuid>",      -- source document (for GDPR deletion)
    "schema_name":  "invoice",
    "source":       "seed" | "correction",
    "input_text":   "<extracted text snippet>",
    "expected_json": { ... },       -- labeled output
    "created_at":   "2026-06-09T..."
}

Payload index on tenant_id (keyword index for exact match filtering):
  - Every query MUST include: filter={"must": [{"key": "tenant_id", "match": {"value": "<uuid>"}}]}
  - The Qdrant Service layer (C-18) enforces this before any query executes.

Why single collection (not per-tenant):
  - Qdrant optimizes single-collection with payload filtering better than many small collections
  - At MVP scale (<100 tenants, <10k vectors per tenant), a single collection is simpler
  - Migration to per-collection if needed is straightforward (Phase 2 evaluation point)

Qdrant Service Guard (REQ-030, EC-001, EC-002):
  class QdrantService:
      async def search(self, tenant_id: str, ...) -> list[ScoredPoint]:
          if not tenant_id:
              logger.critical("Qdrant query attempted without tenant_id",
                              extra={"severity": "CRITICAL"})
              raise TenantFilterMissingError("tenant_id filter is required")
          # Build filter with mandatory tenant_id
          filter = Filter(must=[
              FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
          ])
          results = self.client.search(..., query_filter=filter)
          # Double-check: verify all returned points belong to tenant
          for point in results:
              assert point.payload["tenant_id"] == tenant_id, \
                  f"Cross-tenant vector leak detected: {point.id}"
          return results
```

### 4.4 Data Flow Map

| Producer | Transport | Store | Consumer |
|----------|-----------|-------|----------|
| Client upload | HTTP POST | documents table (PG) + file storage | Ingest Module |
| Ingest Module | Async queue | worker pool | LangGraph Pipeline |
| LlamaParse API | HTTP response | raw_text in state (checkpoint) | Guardrail Node |
| Guardrail Node | State update | guardrail_reports (PG) | Extract Node |
| Qdrant Service | HTTP query | Qdrant vectors | Extract Node (RAG) |
| Claude/GPT-4o | HTTP response | extracted_json in state | Score Node |
| Score Node | State update | extraction_results (PG) | Route Node |
| Route Node | Internal event | review_tasks or dlq (PG) | Review Module or DLQ |
| Webhook Delivery | HTTP POST | webhook_deliveries (PG) | Tenant webhook endpoint |
| Review Module | SQL write | Qdrant + extraction_results | Few-shot RAG + Webhook |
| All components | Function call | audit_log (PG) | Compliance export |

---

## 5. Multi-Tenancy & Isolation Design

### 5.1 Tenant Context Propagation

```
Request Flow:

  1. Client sends request with Authorization: Bearer <JWT> or X-API-Key: <key>
  2. API Gateway middleware:
     a. Validates JWT signature (RS256) or API key hash lookup
     b. Extracts tenant_id from JWT claim or api_keys table
     c. Stores tenant_id in Python contextvars (ContextVar[str])
     d. Sets PostgreSQL session variable: SET LOCAL app.current_tenant_id = '<uuid>'
  3. Every subsequent DB query in this request is filtered by RLS automatically
  4. Every Qdrant query passes tenant_id from contextvar to QdrantService
  5. Every log entry includes tenant_id from contextvar via logging filter
  6. Every audit record includes tenant_id from contextvar

  Worker (background task) flow:
  1. Worker dequeues document with tenant_id
  2. Worker sets contextvar and PG session variable before processing
  3. LangGraph execution inherits the tenant context
  4. All the same guards apply
```

### 5.2 Defense-in-Depth Layers

| Layer | Mechanism | What it prevents |
|-------|-----------|-----------------|
| L1 - API Gateway | JWT/API-key tenant_id extraction | Unauthenticated access |
| L2 - Middleware | contextvar + PG session var | Requests without tenant context |
| L3 - PostgreSQL RLS | Row-level policies on all tables | DB-level cross-tenant data access |
| L4 - Qdrant Service | Mandatory tenant_id filter + post-query assertion | Cross-tenant vector leakage (EC-001) |
| L5 - LLM Prompt Builder | Verifies tenant_id on all RAG results before injection | Cross-tenant examples in prompt (EC-002) |
| L6 - Log Filter | Replaces PII with [REDACTED]; includes tenant_id | PII leakage in logs |

### 5.3 API Key Lifecycle

- Keys stored as SHA-256 hash (key_hash column). Plain key shown once on creation.
- Lookup: hash incoming key, query by key_hash. Index makes this O(1).
- Revocation: set `revoked_at` timestamp. Auth middleware checks `revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now())`.
- 100ms revocation SLA (REQ-032): no cache on API keys at MVP. Direct DB lookup on every request. At 1000 req/min platform-wide (~17 req/s), this is trivially fast with an indexed lookup.
- If caching is needed later: cache with 5s TTL, or use a revocation bloom filter.

---

## 6. Cross-Cutting Concerns

### 6.1 Authentication & Authorization

**JWT (RS256):**
- Tokens issued by an external identity provider (out of scope at MVP; platform issues JWT for pilot).
- Claims: `sub` (user_id), `tenant_id`, `roles` (admin | reviewer | operator), `exp`, `iat`.
- Verification: RS256 public key loaded at startup. No symmetric secrets.
- Token validation middleware rejects: missing token, expired, invalid signature, missing tenant_id claim.

**API Key Auth:**
- Alternative to JWT for programmatic access (machine-to-machine).
- Key format: `ocr_<random_32_bytes_base64>` (prefix for identification).
- Sent via `X-API-Key` header.
- Middleware: hash key, lookup in api_keys table, check not revoked/expired, extract tenant_id.

**Authorization:**
- MVP: role-based at the endpoint level.
  - `extract`, `read` scopes for API keys.
  - `admin` role required for `/api/v1/admin/*` endpoints.
  - `reviewer` role required for review queue actions.
- Tenant boundary enforced by RLS (not application-level authz).

### 6.2 Confidence Scoring Algorithm (REQ-055, EC-003)

```python
def compute_confidence(
    llm_self_confidence: float,       # 0.0 - 1.0 from LLM response
    schema_required_fields: list[str],
    extracted_fields: dict,
    pii_fields: list[str],
    guardrail_multiplier: float,      # 1.0 for PASS, 0.8 for WARN
    schema_config: dict               # per-schema overrides
) -> ConfidenceResult:

    # 1. Completeness score: ratio of required fields present and non-empty
    present = sum(1 for f in schema_required_fields if extracted_fields.get(f))
    completeness = present / len(schema_required_fields) if schema_required_fields else 1.0

    # 2. If ANY required field is missing, force LOW confidence (REQ-004)
    if completeness < 1.0:
        return ConfidenceResult(
            overall=0.0,
            tier="LOW",
            breakdown={"llm": llm_self_confidence, "completeness": completeness,
                       "semantic": 0.0, "guardrail_adjusted": 0.0},
            low_confidence_fields=[f for f in schema_required_fields
                                   if not extracted_fields.get(f)]
        )

    # 3. Semantic validation score (type checks, format checks)
    semantic = validate_field_formats(extracted_fields, schema_config)

    # 4. Combine: min(llm, completeness, semantic) * guardrail_multiplier
    raw = min(llm_self_confidence, completeness, semantic)
    adjusted = raw * guardrail_multiplier

    # 5. Route by configurable thresholds (EC-003: inclusive on upper tier)
    high_threshold = schema_config.get("confidence_high", 0.85)
    medium_threshold = schema_config.get("confidence_medium", 0.60)

    if adjusted >= high_threshold:
        tier = "HIGH"
    elif adjusted >= medium_threshold:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    return ConfidenceResult(
        overall=adjusted,
        tier=tier,
        breakdown={"llm": llm_self_confidence, "completeness": completeness,
                   "semantic": semantic, "guardrail_adjusted": adjusted},
        low_confidence_fields=identify_low_fields(extracted_fields, schema_config)
    )
```

**Boundary semantics (EC-003):**
- `confidence >= 0.85` -> HIGH (inclusive)
- `0.60 <= confidence < 0.85` -> MEDIUM (0.60 inclusive)
- `confidence < 0.60` -> LOW

### 6.3 Guardrail WARN vs BLOCK Escalation (EC-004)

| Guardrail | PASS | WARN | BLOCK |
|-----------|------|------|-------|
| Prompt injection | Text clean | N/A (binary) | Injection detected -> DLQ, text never reaches LLM |
| Text quality | Quality > threshold | Quality marginal (0.8x multiplier) | Empty or corrupt output -> DLQ (PARSE_EMPTY_OUTPUT) |
| File size | Under limit | N/A (binary) | Over 50MB -> 413 at ingest |
| Text length | Sufficient text | Short text (0.8x multiplier) | No extractable text -> DLQ |

**WARN behavior:** Guardrail result recorded. Pipeline continues. Confidence multiplier applied (default 0.8x, configurable per I-005). This may push the document from HIGH to MEDIUM, triggering human review.

**BLOCK behavior:** Pipeline halts immediately. Document written to DLQ. Webhook fires with status REJECTED or ERROR. Audit record created. Blocked text never reaches the LLM.

### 6.4 GDPR Erasure of In-Flight Documents (EC-005, EC-018, REQ-041)

```
Erasure Flow:

  1. DELETE /api/v1/documents/{id} received
  2. Check document exists and belongs to requesting tenant (RLS)
  3. Check document status:
     a. If COMPLETED/REJECTED/ERROR (at rest): standard erasure
     b. If PENDING/PARSING/EXTRACTING/SCORING/ROUTING/DELIVERING (in-flight):
        i.   Set cancellation flag in shared cancellation registry
        ii.  The active worker checks this flag between pipeline nodes
        iii. Worker transitions status to CANCELLED
        iv.  If worker is mid-LLM-call, the call completes but result is discarded
  4. Hard-delete:
     - documents.file_storage_key (delete file from storage)
     - extraction_results for this document
     - guardrail_reports for this document
     - review_tasks for this document
     - dlq entries for this document
     - webhook_deliveries for this document
     - LangGraph checkpoint (thread_id = document_id)
     - Qdrant vectors where document_id matches
  5. Update documents row: status='tombstone', null out all content fields
  6. Insert audit_log record: event_type = ERASURE_IN_FLIGHT or ERASURE_AT_REST

  LLM provider-side logs: Architecture cannot guarantee deletion from
  Claude/GPT-4o provider logs (I-001). This is a legal/DPA concern,
  not an architecture concern. The pii_to_llm_policy tenant config
  controls whether PII reaches the LLM at all.
```

### 6.5 Webhook Retry & DLQ (EC-008, REQ-012)

```
Retry schedule: [1s, 5s, 30s, 120s, 600s] (5 attempts, exponential)

  attempt 1: immediate
  attempt 2: +1s
  attempt 3: +5s
  attempt 4: +30s
  attempt 5: +120s
  (total elapsed: ~156s worst case before DLQ)

  If all 5 fail:
  - Write to DLQ with failure_reason=WEBHOOK_DELIVERY_FAILED, last HTTP status
  - Audit record: event_type=WEBHOOK_EXHAUSTED
  - No further automatic retry

  DLQ retry (POST /api/v1/admin/dlq/{id}/retry):
  - Re-enters pipeline from START (not from webhook step)
  - Idempotency: if DLQ item status != 'pending', return 409 Conflict (REQ-050)
  - Sets DLQ status to 'retrying'
  - On pipeline completion, DLQ status set to 'resolved'
```

### 6.6 LlamaParse Empty/Corrupt Output (EC-006)

- LlamaParse returns HTTP 2xx but empty string or malformed content.
- Text quality guardrail detects: `len(raw_text.strip()) < MIN_TEXT_LENGTH` (default 10 chars).
- Result: BLOCK. DLQ entry with `failure_reason: PARSE_EMPTY_OUTPUT`. Raw output preserved in DLQ pipeline_state for debugging.
- LlamaParse parse retry: up to 3 attempts with exponential backoff (1s, 3s, 9s). Empty output on all retries triggers the BLOCK.

### 6.7 Circuit Breaker for LLM and Parse (REQ-046, REQ-047)

```
Circuit Breaker Configuration:

  LLM Circuit Breaker:
    - failure_threshold: 5 failures in 60s sliding window
    - recovery_timeout: 30s (half-open after 30s)
    - States: CLOSED -> OPEN -> HALF_OPEN -> CLOSED

  When OPEN:
    1. Alert fires within 2 minutes (REQ-046) via configured channel
    2. Audit record: event_type=CIRCUIT_BREAKER_OPEN
    3. Route extraction to fallback LLM (GPT-4o if primary is Claude, vice versa)
    4. If fallback also fails -> DLQ with failure_reason=LLM_UNAVAILABLE (REQ-047)

  LlamaParse Circuit Breaker (separate):
    - failure_threshold: 5 failures in 120s
    - On OPEN: fall back to pdfplumber+pytesseract (degraded accuracy, no DLQ)
    - Alert fires

  Implementation: Custom async circuit breaker using asyncio + time window.
  Not using a library to avoid unnecessary dependency; pattern is simple.

  State is in-memory per worker process. For multi-process/pod deployments,
  each worker independently tracks failures against the same external service.
  This is intentional: avoids shared state complexity, and the failure
  condition (external service down) naturally manifests across all workers.
```

### 6.8 Observability

**Prometheus Metrics (REQ-042):**

| Metric | Type | Labels |
|--------|------|--------|
| `ocr_documents_ingested_total` | Counter | tenant_id, document_type |
| `ocr_documents_completed_total` | Counter | tenant_id, document_type, routing_decision |
| `ocr_documents_rejected_total` | Counter | tenant_id, failure_reason |
| `ocr_extraction_duration_seconds` | Histogram | tenant_id, document_type, step |
| `ocr_llm_tokens_used_total` | Counter | tenant_id, model |
| `ocr_review_queue_depth` | Gauge | tenant_id |
| `ocr_dlq_depth` | Gauge | tenant_id |
| `ocr_webhook_delivery_total` | Counter | tenant_id, status |
| `ocr_circuit_breaker_state` | Gauge | service (llm_primary, llm_fallback, llamaparse) |
| `ocr_worker_queue_depth` | Gauge | tenant_id |

**Structured JSON Logs (REQ-053):**

```json
{
    "timestamp": "2026-06-09T10:30:00.123Z",
    "level": "INFO",
    "service": "ocr-platform",
    "tenant_id": "uuid",
    "document_id": "uuid",
    "event": "extraction_complete",
    "step": "extract",
    "duration_ms": 3200,
    "model_used": "claude-sonnet-4-6",
    "token_usage": {"prompt": 1200, "completion": 400},
    "confidence": 0.92,
    "routing": "HIGH",
    "message": "Extraction completed with HIGH confidence"
}
```

**PII log masking:** A custom logging filter replaces values of fields listed in the schema's `pii_fields[]` with `[REDACTED]` before log emission. Applied globally via Python logging configuration.

**Alert Rules (REQ-048):**

| Alert | Condition | Severity |
|-------|-----------|----------|
| DLQ depth high | `ocr_dlq_depth > 50` for 5 min | P1 |
| Circuit breaker open | `ocr_circuit_breaker_state == 1` (OPEN) | P1 |
| Latency SLA breach | `histogram_quantile(0.95, ocr_extraction_duration_seconds) > 30` | P1 |
| Error rate high | `rate(ocr_documents_rejected_total[5m]) / rate(ocr_documents_ingested_total[5m]) > 0.05` | P1 |
| Review queue stale | Review item age > 24h | P2 |

---

## 7. Deployment Topology

### 7.1 Docker Compose (Development)

```yaml
# docker-compose.yml (simplified)
services:
  api:
    build: .
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL=postgresql+asyncpg://ocr:ocr@postgres:5432/ocr
      - QDRANT_URL=http://qdrant:6333
      - LLAMAPARSE_API_KEY=${LLAMAPARSE_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - JWT_PUBLIC_KEY_PATH=/keys/jwt_public.pem
      - WORKER_CONCURRENCY=10
    depends_on: [postgres, qdrant]

  worker:
    build: .
    command: python -m app.worker
    environment: # same as api
    depends_on: [postgres, qdrant]

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: ocr
      POSTGRES_USER: ocr
      POSTGRES_PASSWORD: ocr
    ports: ["5432:5432"]
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./migrations/init.sql:/docker-entrypoint-initdb.d/init.sql

  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333"]
    volumes:
      - qdrant_data:/qdrant/storage

  prometheus:
    image: prom/prometheus
    ports: ["9090:9090"]
    volumes:
      - ./deploy/prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana
    ports: ["3000:3000"]

  # --- OPTIONAL: uncomment for on-prem LLM ---
  # vllm:
  #   image: vllm/vllm-openai:latest
  #   command: --model mistralai/Mistral-7B-Instruct-v0.3 --port 8001
  #   deploy:
  #     resources:
  #       reservations:
  #         devices:
  #           - driver: nvidia
  #             count: 1
  #             capabilities: [gpu]
```

### 7.2 Kubernetes (Production)

```
Namespace: ocr-platform

Deployments:
  ocr-api          (2+ replicas, HPA on CPU 70%)
  ocr-worker       (4+ replicas, HPA on queue depth)

StatefulSets:
  postgresql       (1 primary + 1 standby, streaming replication)
  qdrant           (1 replica at MVP; 3-node cluster Phase 2)

ConfigMaps:
  ocr-config       (non-secret configuration)
  prometheus-rules (alert rules)

Secrets:
  ocr-secrets      (DB password, API keys for LLM providers, JWT private key)
  tls-cert         (TLS certificate for ingress)

Ingress:
  ocr-ingress      (TLS termination, /api/* -> ocr-api, /metrics -> ocr-api)

CronJob:
  retention-purge  (schedule: "0 2 * * *", runs nightly purge)
  stale-review-check (schedule: "0 * * * *", checks for 24h stale reviews)

PersistentVolumeClaims:
  postgres-data    (100Gi, SSD)
  qdrant-data      (50Gi, SSD)

ServiceMonitor:
  ocr-metrics      (Prometheus scrape config for /metrics)
```

### 7.3 Decision Points by Deployment Mode

| Decision | Cloud (default) | Self-hosted LlamaParse | On-prem (vLLM) |
|----------|----------------|----------------------|----------------|
| LLM provider | Claude + GPT-4o (cloud API) | Claude + GPT-4o (cloud API) | vLLM (local GPU) |
| LlamaParse | Cloud API | Self-hosted container (add to k8s) | Self-hosted container |
| PII policy | ENCRYPT_BEFORE_LLM | ENCRYPT_BEFORE_LLM | ALLOW_PLAINTEXT (data stays on-prem) |
| Fallback LLM | GPT-4o | GPT-4o | Second vLLM instance or none |
| Network | Outbound HTTPS to Anthropic/OpenAI/LlamaParse | Outbound HTTPS to Anthropic/OpenAI | Air-gapped possible |
| Config changes | None | Add llamaparse container, set `PARSER_PROVIDER=llamaparse_local` | Add vLLM container, set `LLM_PROVIDER=vllm`, `LLM_BASE_URL` |

---

## 8. Key Architectural Decisions (ADR Summary)

| D-ID | Decision | Chosen | Rejected | Rationale | Consequence |
|------|---------|--------|---------|-----------|-------------|
| D-001 | Architecture style | Modular monolith | Microservices | Small team, single pipeline, shared PG state; microservices premature at MVP scale | Single deployment unit; future extraction possible along module boundaries |
| D-002 | Workflow engine | LangGraph with PG checkpoint | Celery + Redis, Temporal | LangGraph purpose-built for LLM pipelines; checkpoint-postgres eliminates Redis; matches tech stack | Tied to LangGraph API; checkpoint recovery is node-granular |
| D-003 | Multi-tenancy DB strategy | Shared schema with RLS | Schema-per-tenant, DB-per-tenant | RLS is simplest at <100 tenants; no DDL per onboarding; single connection pool | Must set session var on every connection; admin operations need BYPASSRLS role |
| D-004 | Qdrant tenant isolation | Single collection + payload filter | Collection-per-tenant | Simpler at MVP; Qdrant optimizes filtered search well | Must enforce filter at service layer (C-18); re-evaluate at >100 tenants |
| D-005 | API key storage | SHA-256 hash | bcrypt, plaintext | Fast lookup (indexed), irreversible, no timing attack risk at this scale | Key shown once on creation; lost keys must be regenerated |
| D-006 | Confidence scoring | min(llm, completeness, semantic) * guardrail_multiplier | Weighted average, ML model | Simple, auditable, deterministic; easy to explain to tenants | May not capture cross-field correlations; Phase 2 can add ML scorer |
| D-007 | PII handling for LLM | Configurable per-tenant policy (encrypt/redact/allow) | Always redact, always allow | DPA status varies per tenant; architecture must support all modes | Adds config complexity; default is ENCRYPT_BEFORE_LLM |
| D-008 | Webhook retry strategy | Fixed schedule [1,5,30,120,600]s | Jittered backoff, queue-based | Predictable, simple, matches requirements spec exactly | No jitter may cause thundering herd if many tenants' webhooks fail simultaneously |
| D-009 | Circuit breaker scope | Per-worker-process in-memory | Shared (Redis/PG) | No shared state dependency; external failure manifests across all workers naturally | Slower detection if only one worker hits failures; acceptable at MVP |
| D-010 | PII encryption | AES-256-GCM field-level in JSONB | Column-level PG encryption, pgcrypto | Field-level allows selective encryption of only PII fields; application controls key | Key management responsibility on application; must handle key rotation |
| D-011 | Audit immutability | PG trigger blocking UPDATE/DELETE | Application-only enforcement | DB-level enforcement cannot be bypassed by application bugs | Requires privileged role for GDPR erasure; documented procedure |
| D-012 | Worker concurrency | asyncio.Semaphore per tenant | Celery workers, thread pool | Native async; no broker dependency; semaphore enforces per-tenant limit naturally | Single-process limit; multi-pod scaling via k8s HPA |

---

## 9. Project / Repository Structure

```
ocr_service/
|-- app/
|   |-- __init__.py
|   |-- main.py                         # FastAPI app factory, lifespan
|   |-- config.py                       # Pydantic Settings (env vars)
|   |
|   |-- api/                            # API layer (C-01)
|   |   |-- __init__.py
|   |   |-- dependencies.py             # Depends() for auth, tenant, db session
|   |   |-- middleware/
|   |   |   |-- __init__.py
|   |   |   |-- auth.py                 # JWT + API key validation
|   |   |   |-- tenant_context.py       # Set RLS session var, contextvar
|   |   |   |-- rate_limiter.py         # Per-tenant rate limiting
|   |   |   |-- logging_context.py      # Inject tenant_id/doc_id into logs
|   |   |
|   |   |-- routers/
|   |   |   |-- __init__.py
|   |   |   |-- extract.py             # POST /api/v1/extract (C-02)
|   |   |   |-- schemas.py             # /api/v1/schemas CRUD (C-03)
|   |   |   |-- review.py              # /api/v1/review (C-04)
|   |   |   |-- admin.py               # /api/v1/admin/* (C-05)
|   |   |   |-- audit.py               # /api/v1/audit (C-05)
|   |   |   |-- documents.py           # /api/v1/documents (incl GDPR delete)
|   |   |   |-- health.py              # /health, /metrics
|   |   |
|   |   |-- schemas/                    # Pydantic request/response models
|   |   |   |-- __init__.py
|   |   |   |-- extract.py
|   |   |   |-- schema_registry.py
|   |   |   |-- review.py
|   |   |   |-- admin.py
|   |   |   |-- audit.py
|   |   |   |-- common.py              # ErrorResponse, PaginatedResponse
|   |
|   |-- domain/                         # Domain core (business logic)
|   |   |-- __init__.py
|   |   |-- confidence.py              # Confidence scorer (C-09)
|   |   |-- guardrails/                # Guardrail implementations (C-12)
|   |   |   |-- __init__.py
|   |   |   |-- base.py
|   |   |   |-- injection.py
|   |   |   |-- text_quality.py
|   |   |   |-- text_length.py
|   |   |-- encryption.py             # PII AES-256 encryption (C-08)
|   |   |-- webhook.py                # HMAC signing, retry logic (C-15)
|   |   |-- circuit_breaker.py        # Async circuit breaker (C-19)
|   |
|   |-- pipeline/                       # LangGraph extraction pipeline (C-10)
|   |   |-- __init__.py
|   |   |-- graph.py                   # LangGraph graph definition
|   |   |-- state.py                   # ExtractionState TypedDict
|   |   |-- nodes/
|   |   |   |-- __init__.py
|   |   |   |-- parse.py              # Parse node (C-11)
|   |   |   |-- guardrail.py          # Guardrail node (C-12)
|   |   |   |-- extract.py            # Extract node (C-13)
|   |   |   |-- score.py              # Score node (part of C-09)
|   |   |   |-- route.py              # Route node (C-14)
|   |   |   |-- deliver.py            # Webhook delivery node
|   |   |   |-- dlq_sink.py           # DLQ write node
|   |   |   |-- review_sink.py        # Review queue write node
|   |   |-- parsers/
|   |   |   |-- __init__.py
|   |   |   |-- base.py               # DocumentParser interface
|   |   |   |-- llamaparse.py         # LlamaParse cloud client
|   |   |   |-- local.py              # pdfplumber + pytesseract fallback
|   |   |-- prompts/
|   |   |   |-- __init__.py
|   |   |   |-- builder.py            # Prompt template builder with RAG
|   |   |   |-- templates/            # Default prompt templates
|   |
|   |-- services/                       # Application services (orchestration)
|   |   |-- __init__.py
|   |   |-- ingest.py                  # Ingest service
|   |   |-- schema_registry.py        # Schema CRUD + versioning
|   |   |-- review.py                 # Review queue operations
|   |   |-- admin.py                  # API keys, tenant config
|   |   |-- audit.py                  # Audit log writer (C-07)
|   |   |-- qdrant.py                 # Qdrant service with tenant guard (C-18)
|   |   |-- dlq.py                    # DLQ operations (C-16)
|   |   |-- erasure.py                # GDPR erasure orchestrator
|   |   |-- notification.py           # Stale review + alert notifications (C-21)
|   |
|   |-- db/                            # Database layer
|   |   |-- __init__.py
|   |   |-- session.py                # async SQLAlchemy session factory
|   |   |-- models/                    # SQLAlchemy ORM models
|   |   |   |-- __init__.py
|   |   |   |-- tenant.py
|   |   |   |-- api_key.py
|   |   |   |-- schema.py
|   |   |   |-- document.py
|   |   |   |-- extraction_result.py
|   |   |   |-- guardrail_report.py
|   |   |   |-- review_task.py
|   |   |   |-- audit_log.py
|   |   |   |-- dlq.py
|   |   |   |-- webhook_delivery.py
|   |   |-- repositories/             # Data access layer
|   |   |   |-- __init__.py
|   |   |   |-- base.py               # Generic CRUD with tenant filtering
|   |   |   |-- document.py
|   |   |   |-- schema.py
|   |   |   |-- review.py
|   |   |   |-- audit.py
|   |   |   |-- dlq.py
|   |
|   |-- worker/                        # Background worker (C-17)
|   |   |-- __init__.py
|   |   |-- pool.py                   # Worker pool with per-tenant semaphore
|   |   |-- runner.py                 # Pipeline execution runner
|   |   |-- cancellation.py           # GDPR cancellation registry
|   |
|   |-- observability/                 # Metrics + logging (C-20)
|   |   |-- __init__.py
|   |   |-- metrics.py                # Prometheus metric definitions
|   |   |-- logging.py                # Structured JSON logging config
|   |   |-- pii_filter.py             # Log PII masking filter
|
|-- migrations/                        # Database migrations
|   |-- alembic.ini
|   |-- env.py
|   |-- versions/
|   |   |-- 001_initial_schema.py
|   |   |-- 002_rls_policies.py
|   |   |-- 003_audit_triggers.py
|
|-- deploy/                            # Deployment configs
|   |-- docker-compose.yml
|   |-- docker-compose.override.yml   # Dev overrides
|   |-- Dockerfile
|   |-- kubernetes/
|   |   |-- namespace.yaml
|   |   |-- api-deployment.yaml
|   |   |-- worker-deployment.yaml
|   |   |-- postgres-statefulset.yaml
|   |   |-- qdrant-statefulset.yaml
|   |   |-- ingress.yaml
|   |   |-- configmap.yaml
|   |   |-- secrets.yaml
|   |   |-- hpa.yaml
|   |   |-- cronjob-purge.yaml
|   |   |-- cronjob-stale-review.yaml
|   |-- prometheus.yml
|   |-- grafana/
|   |   |-- dashboards/
|   |   |-- datasources.yaml
|   |-- alerting/
|   |   |-- rules.yaml
|
|-- tests/
|   |-- __init__.py
|   |-- conftest.py                   # Shared fixtures, test DB, test Qdrant
|   |-- unit/
|   |   |-- domain/
|   |   |   |-- test_confidence.py
|   |   |   |-- test_guardrails.py
|   |   |   |-- test_encryption.py
|   |   |   |-- test_circuit_breaker.py
|   |   |-- pipeline/
|   |   |   |-- test_parse_node.py
|   |   |   |-- test_extract_node.py
|   |   |   |-- test_route_node.py
|   |   |-- services/
|   |   |   |-- test_qdrant_service.py
|   |   |   |-- test_audit_service.py
|   |-- integration/
|   |   |-- test_extract_api.py
|   |   |-- test_schema_api.py
|   |   |-- test_review_api.py
|   |   |-- test_admin_api.py
|   |   |-- test_rls.py               # Cross-tenant isolation tests
|   |   |-- test_pipeline_e2e.py
|   |   |-- test_gdpr_erasure.py
|   |-- fixtures/
|   |   |-- sample_invoice.pdf
|   |   |-- sample_receipt.pdf
|   |   |-- corrupt_file.exe
|
|-- docs/
|   |-- PRODUCT_SPEC.md
|   |-- sdlc/
|   |   |-- 01-product-spec.md
|   |   |-- 01-product-spec.ctx.md
|   |   |-- 02-requirements.md
|   |   |-- 02-requirements.ctx.md
|   |   |-- 03-architecture.md         # THIS DOCUMENT
|   |   |-- 03-architecture.ctx.md
|
|-- pyproject.toml                     # Project config, dependencies
|-- .env.example                       # Template environment variables
|-- .gitignore
|-- Makefile                           # Dev commands: make run, make test, make migrate
```

---

## 10. Coding Standards (Python / FastAPI)

### 10.1 Layer Dependency Rules

```
routers  ->  services  ->  repositories  ->  models
                       ->  domain (pure logic)
                       ->  external clients (Qdrant, LLM, LlamaParse)

Routers MUST NOT: call repositories directly, contain business logic, return ORM models
Services MUST NOT: contain HTTP-specific code (Request, Response objects)
Repositories MUST NOT: contain business logic
Domain MUST NOT: import from db, api, or services layers
```

### 10.2 Naming Conventions

| Artifact | Convention | Example |
|---------|-----------|---------|
| Python module | snake_case | `schema_registry.py` |
| Class | PascalCase | `SchemaRegistryService` |
| Function | snake_case verb_noun | `create_schema()` |
| Constant | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` |
| Pydantic model (request) | PascalCase + Request | `CreateSchemaRequest` |
| Pydantic model (response) | PascalCase + Response | `SchemaResponse` |
| DB table | snake_case plural | `extraction_results` |
| DB column | snake_case | `tenant_id` |
| REST endpoint | kebab-case plural noun | `/api/v1/api-keys` |
| Environment variable | UPPER_SNAKE_CASE | `DATABASE_URL` |

### 10.3 Error Handling

```python
# Exception hierarchy
class OCRPlatformError(Exception): pass
class BadRequestError(OCRPlatformError): status_code = 400
class UnauthorizedError(OCRPlatformError): status_code = 401
class ForbiddenError(OCRPlatformError): status_code = 403
class NotFoundError(OCRPlatformError): status_code = 404
class ConflictError(OCRPlatformError): status_code = 409
class UnprocessableError(OCRPlatformError): status_code = 422
class RateLimitError(OCRPlatformError): status_code = 429
class ServiceUnavailableError(OCRPlatformError): status_code = 503

# Standard error response shape
class ErrorResponse(BaseModel):
    status: int
    error: str
    message: str
    path: str
    trace_id: str | None = None
    field_errors: dict[str, str] | None = None
    timestamp: datetime

# One global exception handler in main.py -- no try/catch in routers
```

### 10.4 Testing Strategy

| Layer | Framework | Coverage target |
|-------|-----------|----------------|
| Unit | pytest + unittest.mock | >=90% line + branch on domain/ and services/ |
| Integration | pytest + testcontainers (PG + Qdrant) | Happy path + auth + validation for all endpoints |
| E2E | pytest + httpx (against running stack) | Critical flows: ingest->extract->webhook, review, GDPR erasure |

### 10.5 Logging

- Framework: Python `logging` + `python-json-logger`
- Every log entry: timestamp, level, service, tenant_id, document_id, event, message
- PII filter: custom `logging.Filter` that redacts fields matching schema's `pii_fields[]`
- Never log: API keys, JWT tokens, file contents, extracted PII values

---

## 11. Open Questions (Remaining, Non-Blocking)

| # | Issue | Impact | Owner | Due | Status |
|---|-------|--------|-------|-----|--------|
| I-001 | LLM provider DPA | Cannot launch with PII tenants | Compliance Officer | Before pilot | **Architecture addressed via pii_to_llm_policy; legal resolution pending** |
| I-002 | Invoice required-field set | Default assumed; configurable per schema | Document Engineer | Sprint 1 | Non-blocking |
| I-005 | Guardrail WARN multiplier (0.8x) | May need tuning | Document Engineer | Sprint 2 | Non-blocking; configurable |
| I-006 | Correction-to-few-shot immediate write | Risk of RAG pollution | Product | Sprint 3 | Non-blocking; audit trail enables rollback |
| I-007 | Per-document timeout (60s default) | Needs benchmarking | Platform Operator | Sprint 1 | Non-blocking; configurable per schema |

All three originally blocking issues (I-001, I-003, I-004) are resolved architecturally via abstraction layers and configurable policies. Legal/procurement aspects of I-001 remain the Compliance Officer's responsibility.

---

## 12. Decisions Log

| D-ID | Decision | Chosen | Rejected | Date |
|------|---------|--------|---------|------|
| D-001 | Architecture style | Modular monolith | Microservices | 2026-06-09 |
| D-002 | Workflow engine | LangGraph + PG checkpoint | Celery, Temporal | 2026-06-09 |
| D-003 | Multi-tenancy DB | Shared schema + RLS | Schema-per-tenant | 2026-06-09 |
| D-004 | Qdrant isolation | Single collection + filter | Collection-per-tenant | 2026-06-09 |
| D-005 | API key storage | SHA-256 hash | bcrypt | 2026-06-09 |
| D-006 | Confidence scoring | min() * multiplier | Weighted average | 2026-06-09 |
| D-007 | PII-to-LLM policy | Configurable per tenant | Always redact | 2026-06-09 |
| D-008 | Webhook retry | Fixed schedule [1,5,30,120,600]s | Jittered backoff | 2026-06-09 |
| D-009 | Circuit breaker scope | Per-process in-memory | Shared state (Redis) | 2026-06-09 |
| D-010 | PII encryption | AES-256-GCM field-level | pgcrypto column-level | 2026-06-09 |
| D-011 | Audit immutability | PG trigger | App-only enforcement | 2026-06-09 |
| D-012 | Worker concurrency | asyncio.Semaphore | Celery workers | 2026-06-09 |
