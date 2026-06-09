---
doc: 01-product-spec
agent: product-manager
phase: 1
status: complete
human_doc: 01-product-spec.md
next: [requirements-analyst]
feature: enterprise-ocr-platform
provides:
  stories:
    US-001: "Invoice extraction STP — REST ingest to webhook, LlamaParse+LangGraph+Qdrant RAG, guardrails, confidence routing"
    US-002: "Human-in-the-loop review queue — MEDIUM-confidence docs, inline field editing, corrections to vector DB, audit log"
    US-003: "Self-service doc type onboarding — schema registry API, seed examples to Qdrant, dry-run, versioned activation"
    US-004: "Multi-tenant isolation & API keys — PostgreSQL RLS, Qdrant tenant filter, PII encryption, scoped JWT"
    US-005: "Audit trail & compliance export — append-only PG trigger, NDJSON export, GDPR erasure tombstone"
    US-006: "Dead-letter queue & observability — Prometheus metrics, DLQ API, retry endpoint, LLM circuit-breaker alert"
  metric: ">=90% field F1 on invoices; >=75% STP rate; p95 latency <15s; <$0.05/doc; <2% DLQ rate"
mvp: "Invoice extraction end-to-end (US-001+US-004+US-006) for 1 pilot tenant in Sprint 1-4, then review queue (US-002) and audit (US-005)"
out_of_scope:
  - "SSO/SAML (Phase 3)"
  - "Embedded PDF viewer in review UI (Phase 2)"
  - "Multi-modal vision path (Phase 2)"
  - "Data residency per-tenant region selection (Phase 3)"
  - "Cost optimization / model routing (Phase 3)"
  - "ERP/SAP/QuickBooks connectors"
users: [ops-analyst, document-engineer, tenant-admin, platform-operator, compliance-officer]
top_rice: "US-004 Multi-Tenant Isolation (score 1425)"
constraints:
  - "PostgreSQL RLS enforced at DB layer (not app-only)"
  - "Qdrant queries always include tenant_id filter — enforced at service layer"
  - "LLM never receives examples from a different tenant"
  - "Audit table: append-only via PostgreSQL trigger"
  - "PII fields AES-256 encrypted at rest; masked in all logs"
  - "LlamaParse cloud API at MVP (self-hosted evaluation in Phase 2)"
  - "LangGraph state via langgraph-checkpoint-postgres (no Redis at MVP)"
open:
  - "LlamaParse cloud vs self-hosted decision (Sprint 1 kickoff)"
  - "LLM provider DPA required before pilot launch with any PII tenant"
  - "On-premise deployment requirement from any pilot tenant changes LLM stack to vLLM"
  - "Invoice required-field set to be confirmed with pilot tenant (default: invoiceNumber, invoiceDate, vendorName, totalAmount, currency)"
pull_hint: "Full ACs, RICE math, NFRs, tech stack recommendations, LangGraph workflow diagram → 01-product-spec.md"
---
