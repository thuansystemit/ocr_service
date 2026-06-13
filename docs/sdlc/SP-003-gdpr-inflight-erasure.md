# SP-003 — GDPR in-flight erasure atomicity (Spike)

**Date:** 2026-06-12 · **Sprint:** 5 · **Gates:** T-075/T-076 (Sprint 6 erasure)
**Risk addressed:** "GDPR in-flight erasure partial failure leaves PII behind (REQ-041)."

## Problem

`DELETE /api/v1/documents/{id}` must erase a document that may be **mid-pipeline**.
Erasure spans four stores that cannot share one transaction:

1. Postgres rows (document, extraction_results, guardrail_reports, review_tasks,
   dlq, webhook_deliveries) — **transactional**.
2. The LangGraph **checkpoint** rows for `thread_id = document_id` — Postgres, but
   written by the running pipeline.
3. The blob in **file storage** (local fs / S3).
4. **Qdrant** vectors keyed by `document_id` (from corrections, if any).

A naive "delete each in turn" leaves PII behind if the process dies between steps.

## Design — cancel, then compensating cleanup, tombstone last

**Order matters: stop the producer before deleting, and write the tombstone only
after the externals are gone.**

```
1. SET cancellation flag for document_id  (in-memory registry + documents.status check)
2. Mark documents.status = 'cancelled'      (transactional; pipeline checks between nodes)
3. Wait for the in-flight run to observe cancellation and stop (bounded; or force)
4. Delete external stores (idempotent, retryable):
      a. Qdrant vectors where document_id = :id
      b. blob storage object
5. Delete Postgres rows in one transaction:
      - child rows + document row (FK cascade)
      - LangGraph checkpoint rows for thread_id = :id
      - audit rows for the document EXCEPT tombstones (admin/BYPASSRLS path)
6. INSERT immutable tombstone audit row: event_type = 'ERASURE_COMPLETED'
```

### Why this order
- **Cancel before delete (steps 1–3):** if we deleted first, a still-running node
  could re-insert rows (extraction_results, checkpoint) *after* deletion —
  re-creating PII. Cancelling and draining the producer first closes that race
  (EC-018: erasure wins; a concurrent DLQ retry sees the tombstone and aborts).
- **Externals before Postgres (step 4 before 5):** the Postgres rows are the
  index of what external data exists (storage_key, vector ids). Delete them last
  so a crash mid-erasure leaves a *recoverable* pointer to finish cleanup, rather
  than orphaned PII with no record of where it lives.
- **Tombstone last (step 6):** it is the proof of completion. Writing it only
  after every external + row delete succeeds means "tombstone exists ⇒ erasure
  truly finished."

## Compensating-transaction / partial-failure handling

Each external delete (4a, 4b) is **idempotent** (delete-by-key, "not found" = OK)
and **retryable**. A background **erasure-sweep** job re-drives any document in
`status='cancelled'` without a tombstone:

| Failure point | State left behind | Recovery |
|---------------|-------------------|----------|
| after step 2, before 4 | status=cancelled, data intact | sweep re-runs 4–6 |
| during 4 (Qdrant ok, blob fails) | blob orphan | idempotent retry deletes blob |
| during 5 (rows partially deleted) | rows gone, no tombstone | sweep re-runs 4 (no-op) + 5 (idempotent) + 6 |
| after 5, before 6 | externals + rows gone, no tombstone | sweep writes tombstone (4/5 no-op) |

So the invariant is: **a document is fully erased iff a tombstone exists**, and the
sweep makes the whole sequence eventually-consistent under crashes. No partial
failure can leave PII permanently behind without also leaving a `cancelled`
document for the sweep to finish.

## Decisions (feed into T-075/T-076)

- **D-SP003-1:** Cancellation registry = in-memory `set[document_id]` checked by
  the pipeline between nodes (`state.is_cancelled`), **plus** a re-check of
  `documents.status == 'cancelled'` at each persistence point (covers multi-replica
  where the flag isn't in the worker's memory).
- **D-SP003-2:** External deletes are idempotent and run **before** the Postgres
  delete transaction.
- **D-SP003-3:** A `cancelled`-without-tombstone **erasure sweep** (cron) guarantees
  eventual completion; it is the compensating mechanism, not a 2-phase commit.
- **D-SP003-4:** Checkpoint + audit deletes use the `ocr_admin` BYPASSRLS path
  (already used for retention purge), with the audit immutability trigger disabled
  only for the specific document's non-tombstone rows.
- **D-SP003-5:** `DELETE` returns `202 Accepted` immediately after steps 1–2;
  the externals + tombstone complete asynchronously (and idempotently). The API
  reports erasure status via the tombstone.

## Residual risks

- **R-1:** A wedged pipeline node that never observes cancellation. Mitigation:
  the persistence-point status re-check (D-SP003-1) means even a late-completing
  node writes nothing once status is `cancelled`; the pipeline timeout (T-007)
  bounds how long a node can run.
- **R-2:** Provider-side copies (LlamaParse cloud, LLM provider logs) are outside
  our stores — covered by the I-001 DPA, not by this mechanism.

**Spike outcome:** resolved. The cancel-first + externals-before-rows +
tombstone-last ordering, with an idempotent erasure sweep as the compensating
transaction, gives a crash-safe erasure whose completion invariant is a single
tombstone. T-075/T-076 implement it.
