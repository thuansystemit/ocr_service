# Sprint 1 — Testing Guide

Everything here runs in **Docker** (no local Python needed). Three things you can
verify today:

1. [The automated suite](#1-automated-suite-lint--types--tests) — lint, types, and the RLS/migration/unit tests.
2. [The running stack](#2-run-the-stack-and-hit-the-endpoints) — health, metrics, OpenAPI.
3. [Testing with a PDF file](#3-testing-with-a-pdf-file-document) — what is and isn't possible in Sprint 1, plus a real PDF-parsing check you can run now.

---

## 1. Automated suite (lint + types + tests)

Runs `ruff` → `mypy` → `pytest` (unit + integration) against a throwaway
Postgres 16 and Qdrant. This is the canonical "is Sprint 1 healthy?" command.

```bash
docker compose -f deploy/docker-compose.yml --profile test run --build --rm test
```

Expected tail:

```
All checks passed!
Success: no issues found in 15 source files
18 passed
```

The integration tests (`tests/integration/`) are the important ones — they prove
tenant isolation (Row-Level Security) and audit-log immutability against a real
database, not mocks.

---

## 2. Run the stack and hit the endpoints

```bash
make up          # postgres + qdrant + migrations + api + worker
```

Then:

```bash
curl -s localhost:8000/health            # {"status":"ok","version":"0.1.0"}
curl -s localhost:8000/health/ready      # {"status":"ready","checks":{"postgres":"ok"}}
curl -s localhost:8000/metrics | head    # Prometheus exposition
open  http://localhost:8000/docs         # OpenAPI UI
```

Tear down with `make down`.

> Note: `/docs` will currently show only the health/metrics routes. The
> document/extraction routes are added in Sprint 3.

---

## 3. Testing with a PDF file document

### ⚠️ Read this first

**Sprint 1 cannot extract data from a PDF end-to-end.** There is no upload
endpoint and no extraction pipeline yet. Those are Sprint 3+ deliverables:

| Capability | Sprint | Status |
|------------|--------|--------|
| `POST /api/v1/extract` (upload a PDF) | 3 | ❌ not built |
| LlamaParse / OCR parsing in the pipeline | 3 | ❌ not built |
| LangGraph extraction → JSON fields | 3–4 | ❌ not built |
| Confidence routing, webhook, review | 4–5 | ❌ not built |

So if your goal is "upload `invoice.pdf` and get structured JSON back" — that is
**Sprint 3**. What you can do **today** is confirm the parsing libraries that the
Sprint 3 parser will use actually work on your PDF.

### 3a. PDF parsing sanity check (works today)

The Sprint 1 image already contains `pdfplumber`, `pytesseract`, and the
`tesseract-ocr` binary. The helper script
[`parse_pdf_smoke.py`](./parse_pdf_smoke.py) extracts text from a PDF using them.

```bash
# 1. Build the test image (once); it is tagged ocr-service-test:latest
docker compose -f deploy/docker-compose.yml --profile test build test

# 2. Put a PDF where the container can see it
mkdir -p samples
cp /path/to/your/invoice.pdf samples/

# 3. Run the parse smoke check against it
docker run --rm -v "$PWD/samples:/samples" -v "$PWD/docs:/app/docs" \
  ocr-service-test:latest \
  python docs/sprint1/parse_pdf_smoke.py /samples/invoice.pdf
```

Interpreting the result:

- **Text is printed + `[ok] PDF parsing dependencies are working.`** → the PDF has
  an embedded text layer; the Sprint 3 parser will handle it directly.
- **`[warn] ... looks like a scanned PDF` (exit 3)** → no embedded text. This is a
  scanned/image PDF; the Sprint 3 parser will route it through OCR (LlamaParse in
  the cloud, or the local `pytesseract` fallback).
- **`[error] ...` (exit 2)** → the file isn't a readable PDF.

This is the right way to "test with a PDF file document" at this stage: it tells
you which parsing path your real documents will take before the pipeline exists.

### 3b. What the end-to-end test will look like (Sprint 3 preview)

Once Sprint 3 lands, the full PDF test flow becomes (this **does not work yet** —
it is here so you know what is coming):

```bash
# Provision a tenant + API key (admin tooling, Sprint 2/3)
# Then submit a document:
curl -X POST http://localhost:8000/api/v1/extract \
  -H "Authorization: Bearer <api-key>" \
  -F "schema_name=invoice" \
  -F "file=@samples/invoice.pdf"
# -> 202 Accepted, {"document_id": "..."}

# Poll for the result:
curl http://localhost:8000/api/v1/documents/<document_id> \
  -H "Authorization: Bearer <api-key>"
# -> extracted_json, confidence, routing_decision, guardrail reports
```

When that flow is implemented, this guide will be updated with a ready-to-run
invoice fixture and the expected JSON output.

---

## Troubleshooting

| Symptom | Cause / fix |
|--------|-------------|
| `test` run shows old code / old errors | You omitted `--build`. Always pass `--build` so the image picks up edits. |
| Integration tests skipped | Postgres wasn't reachable; the `db_available` fixture skips them. Use the compose `test` service so Postgres is started + healthy first. |
| `ocr-service-test:latest` not found | Build it first: `docker compose -f deploy/docker-compose.yml --profile test build test`. |
| Port 5432/6333/8000 already in use | Stop the conflicting service or change the host port mappings in `deploy/docker-compose.yml`. |
