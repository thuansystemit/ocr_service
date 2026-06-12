# Sprint 4 — LLM Extraction + RAG + Confidence (Summary)

**Status:** ✅ Complete and verified in Docker (ruff + mypy + **98 tests** green against Postgres 16).
**Goal:** The document actually gets understood — RAG-grounded LLM extraction, confidence scoring, and straight-through processing.

## What shipped

| Task | What | Where |
|------|------|-------|
| T-039 | **Qdrant service (C-18)** — mandatory `tenant_id` filter + post-query assertion + tenant-stamped upsert (the cross-tenant leakage guard) | `app/services/qdrant.py` |
| T-040 | RAG few-shot retrieval (embed → tenant+schema-filtered Qdrant query) + extraction prompt builder | `app/pipeline/prompts.py`, `app/domain/embeddings.py` |
| T-041 | **LangChain extraction chain** — provider-agnostic `BaseChatModel`, structured `LLMExtraction` output, injectable model | `app/pipeline/extraction.py`, `app/domain/llm.py` |
| T-051 | **Confidence scorer (C-09)** — `min(llm, completeness, semantic) x guardrail_mult`, upper-tier-inclusive routing | `app/domain/confidence.py` |
| T-052 | Real `extract`/`score` nodes wired into the graph; routing on real confidence | `app/pipeline/nodes.py` |
| T-055 | **Webhook payload signing** — HMAC-SHA256, canonical JSON, `X-OCR-Signature` | `app/domain/webhook.py` |
| T-038 | **LlamaParse cloud client** — async HTTP, 3× retry, fall back to local parser | `app/pipeline/parsers/llamaparse.py` |
| T-064 | **Review queue API** — `GET /api/v1/review`, `GET /api/v1/review/{id}` | `app/api/routers/review.py` |
| — | PII encryption of `pii_fields` applied when persisting extraction results | `app/worker/runner.py` |

## Verification

```
ruff check ........... All checks passed!
mypy ................. Success: no issues found in 53 source files
pytest ............... 98 passed
```

The end-to-end ingest test now drives a PDF to a **`completed`** outcome
(straight-through processing) with an injected fake LLM, and a companion test
proves an LLM failure routes to the DLQ with `EXTRACTION_FAILED`.

## How it's testable without API keys (the design that matters)

Everything external is behind an injectable seam, so CI needs **no** real keys and
production uses real providers:

| External dependency | Seam | Test double |
|---------------------|------|-------------|
| LLM (Claude/GPT-4o) | `set_extraction_chain()` / `ExtractionChain(model=…)` | fake chain / fake model |
| Embeddings (OpenAI) | `set_embedder()` | RAG degrades to zero-shot on failure |
| Qdrant | `QdrantService(client=…)` | fake client (incl. a poisoned cross-tenant point) |
| LlamaParse cloud | `_call_cloud` + injected fallback | mocked, asserts retry→fallback |

## Security highlight — the Qdrant guard (EC-001/002)

`QdrantService` enforces three things no caller can bypass: (1) a query without a
`tenant_id` raises `TenantFilterMissingError`; (2) every returned point's
`tenant_id` is re-checked and a mismatch raises `CrossTenantLeakageError` +
CRITICAL log; (3) upserts always stamp the tenant. All three are covered by
`tests/unit/test_qdrant_service.py`, including a test that feeds a leaked
cross-tenant point and asserts it's rejected.

## Still deferred (by plan)

- **Real LlamaParse cloud latency/limits** — interface + retry/fallback are done
  and tested; live numbers need a cloud account (SP-002 follow-up, gated by I-003).
- **Webhook *delivery* node** (async POST + retry schedule) — Sprint 5 (T-056);
  Sprint 4 ships the signing core only.
- **Full guardrails** (injection/quality/length) — Sprint 5.
- **Circuit breaker + GPT-4o fallback** — Sprint 5 (T-062).
- **Review *actions*** (accept/correct/reject) — Sprint 6 (T-065).
- **Semantic confidence via cosine-vs-seeds** — currently a low-confidence-field
  proxy; full cosine scoring is a refinement.

## Testing

```bash
docker compose -f deploy/docker-compose.yml --profile test run --build --rm test
```

To run a **real** extraction end-to-end, set `ANTHROPIC_API_KEY` (and
`OPENAI_API_KEY` for RAG embeddings) and submit a PDF as in
`docs/sprint3/TESTING.md` — a confident extraction now returns `completed` with
the structured fields instead of routing to the DLQ.
