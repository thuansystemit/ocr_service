# Sprint 5 — Production Hardening (Summary)

**Status:** ✅ Complete and verified in Docker (ruff + mypy + **117 tests** green against Postgres 16).
**Goal:** Guardrails, webhook delivery + retry, DLQ, circuit breaker, audit trail — make the pipeline safe to run unattended.

## What shipped

| Task | What | Where |
|------|------|-------|
| T-071 | **Audit service (C-07)** — `append_event` with SHA-256 payload hash; called on every terminal pipeline transition (append-only via PG trigger) | `app/services/audit.py` |
| T-045/046/047 | **Guardrails (C-12)** — `GuardrailBase`, injection detection (BLOCK), text-quality (empty→BLOCK, short/garbled→WARN) | `app/domain/guardrails/` |
| T-048 | **Guardrail node** — runs all guards, aggregates WARN multipliers, BLOCK → DLQ; reports persisted | `app/pipeline/nodes.py` |
| T-062 | **Circuit breaker (C-19)** — 5 failures/60s → OPEN, cooldown→half-open; Claude failures trip it and fall back to GPT-4o | `app/domain/circuit_breaker.py`, `app/pipeline/extraction.py` |
| T-055/056/057 | **Webhook delivery** — HMAC-signed POST, `[1,5,30,120,600]s` retry, records `webhook_deliveries`, exhaustion → DLQ + audit; fired for completed docs | `app/services/webhook_delivery.py` |
| T-059/060/061 | **DLQ API** — `GET /dlq`, `GET /dlq/{id}`, `POST /dlq/{id}/retry` (409 idempotency) | `app/api/routers/dlq.py` |
| SP-003 | GDPR in-flight erasure compensating-transaction design — **resolved** | `docs/sdlc/SP-003-gdpr-inflight-erasure.md` |

## Verification

```
ruff check ........... All checks passed!
mypy ................. Success: no issues found in 62 source files
pytest ............... 117 passed
```

## How the guardrails change routing (worth knowing)

Guardrails run on parsed text *before* the LLM:

- **BLOCK** (prompt injection, empty text) halts the pipeline — the text never
  reaches the model — and routes to the DLQ (`INJECTION_DETECTED` / `GUARDRAIL_BLOCK`).
- **WARN** (short or garbled text) proceeds but multiplies the final confidence by
  0.8 (per WARN). So a short document that the LLM extracts confidently can still
  drop from HIGH to MEDIUM and land in human review instead of straight-through.

This is why the end-to-end tests use a full-length invoice body — a tiny
`"Invoice 42"` string trips the low-word-count WARN and would route to review.

## Circuit breaker + fallback

The extraction chain runs the primary model (Claude) inside a per-process circuit
breaker. Repeated failures OPEN the breaker; while OPEN (and on any single primary
error) extraction falls back to GPT-4o. After the cooldown the breaker half-opens
and a success closes it. Per-process by design (D-009) — no Redis.

## SP-003 — GDPR in-flight erasure (the hard one)

The spike resolved the atomicity problem across four non-transactional stores
(Postgres rows, LangGraph checkpoints, blob storage, Qdrant). The design:
**cancel the producer first → delete externals before Postgres rows → write the
tombstone last**, with an idempotent **erasure sweep** as the compensating
transaction. The completion invariant is simple: *a document is fully erased iff a
tombstone exists*. Implementation is Sprint 6 (T-075/076).

## Still deferred (by plan)

- **GDPR in-flight erasure implementation** — Sprint 6 (design done here).
- **Review actions** (accept/correct/reject + few-shot write-back) — Sprint 6.
- **Schema versioning + activation** — Sprint 6.
- **Audit export API**, **retention purge**, **stale-review notifications**,
  **observability dashboards** — Sprint 6.

## Testing

```bash
docker compose -f deploy/docker-compose.yml --profile test run --build --rm test
```

New coverage: guardrails (injection/quality/aggregation), circuit breaker
(open/reset/half-open), webhook delivery (success + exhaustion→DLQ), DLQ API
(list/detail/retry-409/404), audit (hash stability + append).
