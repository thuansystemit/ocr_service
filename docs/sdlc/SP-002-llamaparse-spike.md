# SP-002 — LlamaParse cloud: latency, rate limits, fallback (Spike)

**Date:** 2026-06-12 · **Sprint:** 3 · **Gates:** T-038 (Sprint 4 LlamaParse client)
**Risk addressed:** "LlamaParse cloud latency/rate limits blow the 15s p95 SLA (I-003)."

## Questions

1. Is LlamaParse cloud latency for a 2-page invoice within the STP budget (parse
   must leave ≥10s for guardrails + LLM extraction inside the 15s p95)?
2. What are the rate limits, and how do we stay under them at 100 docs/min/tenant?
3. What does the error/timeout surface look like, and does the local fallback
   produce usable text on the same documents?

## Findings & decisions (feed into T-038)

**1. Parser is behind an interface already (D-SP002-1).** Sprint 3 shipped
`DocumentParser` with a working `LocalParser` (pdfplumber + pytesseract). The
cloud client is a drop-in implementing the same `parse()` contract, selected by
`OCR_PARSER_BACKEND`. So the cloud-vs-self-hosted decision (I-003) does **not**
block the pipeline — it is a config/deploy choice, and the local backend is a
always-available fallback.

**2. Budget allocation (D-SP002-2).** Target: parse ≤ 6s p95 for a 2-page PDF,
leaving ≥9s for the rest of the 15s SLA. The T-038 client must:
- set an explicit per-request timeout (default 8s) and treat timeout as a soft
  failure → fall back to `LocalParser` rather than failing the document;
- retry transient 5xx up to 3× with jittered backoff, but **only within the parse
  budget** — once the budget is blown, fall back immediately.

**3. Fallback chain (D-SP002-3).** `LlamaParse cloud → pdfplumber → pytesseract`
(EC-006). Each downgrade is recorded in `state.parse_method` and emitted as a
`WARN`-level structured log + a guardrail note, so degraded parses are visible in
metrics and don't silently lower extraction quality.

**4. Rate limits (D-SP002-4).** The per-tenant worker-pool concurrency cap
(default 10) plus the ingest queue cap (`max_queue_size`) already bound the call
rate into LlamaParse. T-038 adds a shared async semaphore around the cloud client
sized to the negotiated plan limit, and surfaces 429s from LlamaParse as a
ret*-after fallback to local parsing rather than a document failure.

**5. Validation status.** Live latency/limit numbers require a LlamaParse cloud
account + the I-003 hosting decision, which are pending (commercial/compliance).
Because the interface + local fallback are in place, **this does not block Sprint
4**: T-038 implements the client against these decisions and the SP-002 budget,
and the local backend covers any environment without cloud access (incl. on-prem,
I-004).

## Residual / follow-ups

- **R-1:** Confirm actual cloud p95 once an account exists; if it exceeds the 6s
  parse budget on real invoices, default `OCR_PARSER_BACKEND=local` or pursue a
  self-hosted LlamaParse (I-003).
- **R-2:** DPA coverage for sending document bytes to LlamaParse cloud is the same
  I-001 legal gate as the LLM providers; honor `pii_to_llm_policy` for the parse
  step too (redact/encrypt before cloud parse where required).

**Spike outcome:** resolved enough to unblock. The interface + local fallback
de-risk I-003; T-038 builds the cloud client to the 6s parse budget with a
defined fallback and rate-limit strategy.
