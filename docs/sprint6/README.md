# Sprint 6 — MVP Completion (Summary)

**Status:** ✅ Complete and verified in Docker (ruff + mypy + **126 tests** green against Postgres 16).
**Goal:** Close the MVP — schema lifecycle, human review actions, GDPR erasure, audit export. Milestone **M-4: pilot-ready**.

## What shipped

| Task | What | Where |
|------|------|-------|
| T-027/028/029 | **Schema lifecycle** — seed upload (→ Qdrant + `seed_count`), activation gate (≥3 seeds), version snapshot to `schema_versions` | `app/services/schema_registry.py`, `app/api/routers/schemas.py` |
| T-065/066 | **Review actions** — `POST /review/{id}` accept/correct/reject; corrections update the record + write a corrected few-shot back to Qdrant (active learning); optimistic locking → 409 | `app/services/review.py`, `app/api/routers/review.py` |
| T-067 | Stale-review counter (>24h pending) | `app/services/review.py` |
| T-036/075/076 | **GDPR in-flight erasure** — `DELETE /documents/{id}`: cancel → delete blob/Qdrant/checkpoints → cascade-delete rows → tombstone | `app/services/erasure.py`, `app/worker/cancellation.py` |
| T-072 | **Audit export** — `GET /audit/export?format=ndjson\|csv`, streamed, tenant-scoped | `app/api/routers/audit.py` |

## Verification

```
ruff check ........... All checks passed!
mypy ................. Success: no issues found in 66 source files
pytest ............... 126 passed   (82% coverage)
```

## GDPR erasure — how it stays crash-safe (SP-003 realized)

`erase_document` runs the SP-003 sequence: **cancel the producer → delete
externals (blob, Qdrant vectors, LangGraph checkpoints) → cascade-delete Postgres
rows → write the tombstone last.** Two design facts make it simpler than it looks:

1. **`audit_log` stores only a SHA-256 hash, never PII** — so audit rows are not
   personal data and are kept (the trail, including the tombstone, survives
   erasure). This is also why erasure needs **no** BYPASSRLS admin role; it all
   runs in the tenant's RLS-scoped session.
2. A **resurrection guard** in the pipeline runner (`document.status in
   ('cancelled','tombstone')` + the cancellation registry) means a run that was
   mid-flight when erasure began will not write rows that re-create PII.

Tested by `tests/integration/test_erasure.py`: after `DELETE`, the document +
cascaded extraction are gone, `GET` is 404, and exactly one `ERASURE_COMPLETED`
tombstone remains.

## What's intentionally NOT in this build

The estimation's Sprint 6 also lists the exhaustive **51-Gherkin integration
sweep** (T-077–T-084) and operational extras (Grafana dashboards, OpenTelemetry
tracing, the retention-purge cron, SSO). The MVP **features** are complete and
each is covered by focused unit + integration tests (126 total); the full
end-to-end Gherkin matrix and production dashboards are the pre-launch hardening
pass, not new functionality.

## Testing

```bash
docker compose -f deploy/docker-compose.yml --profile test run --build --rm test
```
