---
doc: 08-sprint-plan
agent: planner
phase: 3
status: complete
human_doc: 08-sprint-plan.md
source: [02-requirements, 05-estimation]
next: [tdd-guide, java-developer, angular-frontend-engineer]
provides:
  sprints: 6
  sprint1:
    goal: "Foundation + data layer + RLS — authenticated request in tenant-scoped DB"
    tasks: [T-001, T-002, T-003, T-004, T-005, T-006, T-007, T-008, T-009, T-010, SP-004]
    points: 29
    stories: [US-004, NFR]
    owners: { Lead: [T-001, T-004, SP-004], Mid: [T-003, T-006, T-009, T-010], MidJunior: [T-002, T-005, T-007, T-008] }
  sprint2:
    goal: "Auth complete + PII encryption + LangGraph foundation (SP-001 resolved)"
    tasks: [T-011, T-012, T-013, T-014, T-015, T-016, T-017, T-018, T-032, SP-001]
    points: 29
    stories: [US-004, NFR]
  sprint3:
    goal: "Ingest API + STP happy path compilable + schema registry CRUD"
    tasks: [T-019, T-020, T-021, T-022, T-023, T-024, T-025, T-026, T-033, T-034, SP-002]
    points: 28
    stories: [US-001, US-003]
  sprint4:
    goal: "Full extraction pipeline + confidence routing + review queue wired"
    tasks: [T-035, T-038, T-039, T-040, T-041, T-051, T-052, T-055, T-064]
    points: 31
    stories: [US-001, US-002, US-006]
  sprint5:
    goal: "Guardrails + webhook hardening + DLQ + circuit breaker + audit service"
    tasks: [T-045, T-046, T-047, T-048, T-056, T-057, T-059, T-060, T-062, T-071, SP-003]
    points: 28
    stories: [US-001, US-005, US-006]
  sprint6:
    goal: "GDPR in-flight + schema registry complete + review actions + observability + integration sweep"
    tasks: [T-027, T-028, T-029, T-036, T-037, T-042, T-043, T-044, T-049, T-050, T-053, T-054, T-058, T-061, T-063, T-065, T-066, T-067, T-068, T-069, T-070, T-072, T-073, T-074, T-075, T-076, T-077, T-078, T-079, T-080, T-081, T-082, T-083, T-084, T-030, T-031]
    points: 30
    stories: [US-002, US-003, US-005, US-006, NFR]
milestones:
  - "M-0 End Sprint 1: dev environment live, RLS pass, CI green"
  - "M-1 End Sprint 3: STP happy path demo — invoice PDF in, webhook out, <15s p95"
  - "M-2 End Sprint 4: invoice-in/webhook-out pilot core, review queue, DLQ, circuit breaker"
  - "M-3 End Sprint 5: feature-complete — guardrails, audit, GDPR at-rest, schema seeds"
  - "M-4 End Sprint 6: pilot-ready MVP — GDPR in-flight, all 51 Gherkin scenarios pass, observability"
dod:
  - "Unit tests passing; >=80% coverage new code"
  - "Integration test: happy path + error case"
  - "Alembic migration written + verified (upgrade/downgrade) for any DB change"
  - "Cross-tenant isolation test if task touches tenant-scoped table"
  - "No PII in logs; AES-256-GCM encryption on pii_fields[]"
  - "audit_service.append_event() called for every state-changing operation"
  - "Prometheus metric updated (counter/histogram)"
  - "Structured JSON log at every pipeline node entry/exit (tenant_id + document_id)"
  - "No secrets in code; config via pydantic-settings"
  - "Code review approved by >=1 engineer"
  - "ruff lint + mypy type-check zero new errors"
constraints:
  - "RLS enforced at DB layer on all 10 tenant-scoped tables"
  - "Qdrant queries always include tenant_id filter; post-query assertion mandatory"
  - "LLM prompt never includes cross-tenant few-shot examples"
  - "Audit table append-only via PG trigger (no UPDATE/DELETE)"
  - "PII AES-256-GCM encrypted; [REDACTED] in all log output"
  - "Confidence boundaries: HIGH >=0.85, MEDIUM >=0.60, LOW <0.60"
  - "Webhook retry: 5 attempts exponential backoff [1,5,30,120,600]s"
  - "GDPR erasure cancels in-flight pipelines atomically"
  - "DLQ retry idempotent (409 on re-retry of in-flight)"
  - "Schema activation requires >=3 seed examples"
blockers:
  - "I-001: LLM provider DPA must be signed before PII tenant pilot (legal track parallel from Sprint 1)"
  - "SP-001: LangGraph checkpoint-postgres recovery semantics must be confirmed before T-034 (Sprint 2)"
  - "SP-004: RLS adversarial test result must gate T-010 merge (Sprint 1)"
  - "I-003: LlamaParse cloud vs self-hosted decision required before Sprint 3 Day 1"
  - "I-002: Invoice required field set must be confirmed by pilot tenant before Sprint 4 (gates T-051)"
open:
  - "I-005: WARN confidence multiplier (0.8x) needs eval validation (Sprint 4)"
  - "I-007: 60s pipeline timeout needs benchmarking (Sprint 3 during LangGraph integration)"
  - "DM-001: webhook_secret encryption-at-rest design (Sprint 2 in T-016/T-018)"
  - "DM-002: file storage local vs S3 decision needed before T-022 (Sprint 3)"
pull_hint: "full 6-sprint backlog table, parallelization matrix, dependency graph, per-sprint risk gates -> 08-sprint-plan.md"
---
