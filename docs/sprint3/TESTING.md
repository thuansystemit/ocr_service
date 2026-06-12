# Sprint 3 — Driving a PDF Through the Live API

After Sprint 3 you can actually submit a PDF and watch it flow through the
pipeline (parse → … → route) end to end. Reminder: field **extraction** is a
Sprint 4 stub, so the document currently lands in the DLQ with `LOW_CONFIDENCE` —
that's the expected Sprint 3 outcome (it proves the whole machine runs).

## 1. Automated suite (canonical)

```bash
docker compose -f deploy/docker-compose.yml --profile test run --build --rm test
# ruff + mypy + 70 tests (incl. end-to-end pipeline) against Postgres 16
```

## 2. By hand against the running stack

```bash
make up   # postgres + qdrant + migrations 001-005 + api + worker
```

### a. Mint a key + create an ACTIVE schema

Use the helper + psql (see `docs/sprint2/AUTH.md` for detail). A document can only
be ingested against an **active** schema, and activation requires `seed_count >= 3`
(DB trigger), so seed it active directly for the demo:

```bash
docker compose -f deploy/docker-compose.yml exec api \
  python -c "from app.services.auth import generate_api_key; r,p,h=generate_api_key(); print(r); print(p); print(h)"
```

```bash
docker compose -f deploy/docker-compose.yml exec postgres \
  psql -U postgres -d ocr <<'SQL'
\set t '22222222-2222-2222-2222-222222222222'
SET LOCAL app.current_tenant_id = :'t';
INSERT INTO tenants (id,name,slug,webhook_secret)
  VALUES (:'t','Acme','acme','dev-webhook-secret') ON CONFLICT DO NOTHING;
INSERT INTO api_keys (tenant_id,key_hash,key_prefix) VALUES (:'t','<HASH>','<PREFIX>');
INSERT INTO schemas (tenant_id,name,json_schema,status,seed_count)
  VALUES (:'t','invoice','{}'::jsonb,'active',3);
SQL
```

### b. Submit a PDF

```bash
RAW=ocr_xxxx...   # from the helper

curl -s -X POST http://localhost:8000/api/v1/extract \
  -H "Authorization: Bearer $RAW" \
  -F "schema_name=invoice" \
  -F "file=@samples/invoice.pdf"
# {"document_id":"...","status":"pending"}
```

### c. Poll for the outcome

```bash
DOC=...   # document_id from above
curl -s http://localhost:8000/api/v1/documents/$DOC \
  -H "Authorization: Bearer $RAW" | python -m json.tool
# status transitions pending -> ... -> "rejected", routing_decision "LOW"
# (Sprint 4 turns this into a real "completed" extraction.)
```

What this proves: the file was stored, a `documents` row created, the LangGraph
pipeline ran (parse extracted text, guardrail/extract/score/route executed), the
run was checkpointed in Postgres (`thread_id = document_id`), and the terminal
outcome was persisted.

## 3. Validation error responses

| Case | Response |
|------|----------|
| No `Authorization` | 401 |
| File > size limit | 413 |
| Bad/unsupported MIME | 422 |
| Unknown / inactive schema | 422 |
| Tenant over `max_queue_size` | 429 + `Retry-After` |

## 4. Schema registry

```bash
# create (draft)
curl -s -X POST http://localhost:8000/api/v1/schemas \
  -H "Authorization: Bearer $RAW" -H "Content-Type: application/json" \
  -d '{"name":"receipt","json_schema":{"type":"object"},"required_fields":[]}'

curl -s http://localhost:8000/api/v1/schemas -H "Authorization: Bearer $RAW"
```

Schemas are tenant-isolated by RLS — another tenant's key sees only its own.
