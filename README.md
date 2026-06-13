# OCR Service

Enterprise OCR / document-extraction platform. Documents (PDF/image/DOCX) are
parsed with **LlamaParse**, run through a stateful **LangGraph** extraction
pipeline that calls an LLM via **LangChain** with tenant-scoped few-shot examples
retrieved from a **Qdrant** vector store, validated by a guardrail pipeline,
confidence-scored, and routed (auto-deliver / human review / dead-letter). Built
multi-tenant from the ground up (PostgreSQL Row-Level Security + Qdrant payload
isolation).

> Status: **MVP complete (pilot-ready)** — full ingest → parse → guardrails →
> RAG-grounded LLM extraction → confidence routing → webhook / human review /
> dead-letter, plus auth, PII encryption, audit trail, and GDPR erasure. Verified
> in Docker (ruff + mypy + 126 tests against Postgres 16). See
> [`docs/MVP_STATUS.md`](docs/MVP_STATUS.md) for the full capability + test matrix.

The full SDLC design lives under [`docs/sdlc/`](docs/sdlc/): product spec,
requirements, architecture, data model, estimation, and the sprint plan; each
sprint is summarized under [`docs/sprintN/`](docs/).

## Requirements

- Docker + Docker Compose (the supported way to run and test)
- Python 3.12+ (only if running outside Docker)

## Quick start (Docker)

```bash
make up        # build + start postgres, qdrant, run migrations, api, worker
make logs      # tail logs
make down      # stop
```

The API serves:

- `GET /health` — liveness
- `GET /health/ready` — readiness (checks Postgres)
- `GET /metrics` — Prometheus exposition
- `GET /docs` — OpenAPI UI

## Testing (Docker)

Runs ruff, mypy, and the unit + integration suite against a real Postgres 16
(the integration tests exercise Row-Level Security tenant isolation and the
append-only audit log):

```bash
docker compose -f deploy/docker-compose.yml --profile test run --rm test
```

## Local development (optional, needs Python 3.12)

```bash
make install      # pip install -e ".[dev]"
make migrate      # apply migrations (needs a running postgres)
make test         # unit tests only (no live infra)
make lint typecheck
make run          # uvicorn with reload
```

## Configuration

Copy `.env.example` to `.env` and adjust. All app settings are `OCR_`-prefixed;
see [`app/config.py`](app/config.py).

## Configuring the LLMs

The pipeline uses three model roles, each with a selectable **provider**
(`anthropic` | `openai` | `ollama`). **API keys use their native names** (no
`OCR_` prefix); **provider/model selection uses the `OCR_` prefix.**

| Role | Setting | Default | LangChain class |
|------|---------|---------|-----------------|
| Primary extraction | `OCR_LLM_PROVIDER` + `OCR_LLM_PRIMARY_MODEL` | `anthropic` / `claude-sonnet-4-6` | `ChatAnthropic` / `ChatOpenAI` / `ChatOllama` |
| Fallback extraction | `OCR_LLM_FALLBACK_PROVIDER` + `OCR_LLM_FALLBACK_MODEL` | `openai` / `gpt-4o` | used when the primary trips the circuit breaker |
| Embeddings (RAG) | `OCR_EMBEDDING_PROVIDER` | `openai` (`text-embedding-3-small`) | `OpenAIEmbeddings` / `OllamaEmbeddings` |

### Environment variables

```bash
# --- Provider API keys (native names, NO OCR_ prefix; blank for Ollama) ---
ANTHROPIC_API_KEY=sk-ant-...     # when OCR_LLM_PROVIDER=anthropic
OPENAI_API_KEY=sk-...            # when provider/embeddings = openai
LLAMA_CLOUD_API_KEY=llx-...      # optional: LlamaParse cloud parsing

# --- Provider + model selection (OCR_ prefix) ---
OCR_LLM_PROVIDER=anthropic       # anthropic | openai | ollama
OCR_LLM_PRIMARY_MODEL=claude-sonnet-4-6
OCR_LLM_FALLBACK_PROVIDER=openai # anthropic | openai | ollama
OCR_LLM_FALLBACK_MODEL=gpt-4o
OCR_EMBEDDING_PROVIDER=openai    # openai | ollama
OCR_EMBEDDING_DIM=1536           # must match the embedding model + Qdrant collection
OCR_PARSER_BACKEND=local         # "local" (pdfplumber/OCR) or "llamaparse" (cloud)

# --- Ollama (local / self-hosted) ---
OCR_OLLAMA_BASE_URL=http://localhost:11434
OCR_OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

### Using Ollama (local / self-hosted, no cloud keys)

Run a tool/JSON-capable model so structured extraction works
(`with_structured_output`), e.g.:

```bash
ollama pull llama3.1
ollama pull nomic-embed-text     # for RAG embeddings
```

Then point the platform at it:

```bash
export OCR_LLM_PROVIDER=ollama
export OCR_LLM_PRIMARY_MODEL=llama3.1
export OCR_LLM_FALLBACK_PROVIDER=ollama
export OCR_LLM_FALLBACK_MODEL=llama3.1
export OCR_EMBEDDING_PROVIDER=ollama
docker compose -f deploy/docker-compose.yml up -d --build
```

**The Ollama host depends on where it runs, relative to the container:**

| Ollama runs on… | `OCR_OLLAMA_BASE_URL` |
|---|---|
| Your host (Docker Desktop) | `http://host.docker.internal:11434` *(not `localhost` — inside a container that is the container)* |
| Another machine / server | `http://<server-ip>:11434` |
| App run **outside** Docker | `http://localhost:11434` |

> The compose file defaults `OCR_OLLAMA_BASE_URL` to `http://host.docker.internal:11434`
> so a host-run Ollama works out of the box. On Linux without Docker Desktop, add
> `extra_hosts: ["host.docker.internal:host-gateway"]` to the api/worker services
> or use the host's LAN IP.

### How it behaves

- **Primary + fallback (circuit breaker).** Extraction calls Claude inside a
  per-process circuit breaker. On repeated failures (5 in 60 s) the breaker OPENs
  and extraction falls back to GPT-4o until it cools down. Configure the two model
  ids independently with `OCR_LLM_PRIMARY_MODEL` / `OCR_LLM_FALLBACK_MODEL`.
- **RAG embeddings.** Few-shot retrieval and seed upload embed text with OpenAI.
  If `OPENAI_API_KEY` is unset, retrieval degrades gracefully to **zero-shot**
  (extraction still runs, just without few-shot examples) — it never fails the
  document.
- **No keys at all.** The pipeline parses locally and the extract step fails →
  the document routes to the **dead-letter queue** (`EXTRACTION_FAILED`). This is
  the expected behaviour with no provider configured; set the keys to get real
  `completed` extractions.
- **Swapping providers.** Extraction goes through LangChain's `BaseChatModel`
  abstraction (`app/domain/llm.py`), so switching between Anthropic, OpenAI, and
  Ollama is just `OCR_LLM_PROVIDER` + a model id — no code change. You can mix
  them (e.g. primary `ollama`, fallback `openai`).

### Setting them for the Docker stack

The compose file passes these through from your shell, so export them before
bringing the stack up (or put them in your `.env`):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
docker compose -f deploy/docker-compose.yml up -d --build
```

> Per-tenant overrides: a tenant's row carries a `pii_to_llm_policy` controlling
> whether declared PII fields are encrypted/redacted before reaching the model
> (see `app/config.py` and the architecture doc). The model ids above are the
> platform defaults.

## Project layout

```
app/
  api/            FastAPI routers, middleware, request/response schemas
  domain/         business logic (confidence, guardrails, encryption, webhook)
  pipeline/       LangGraph graph, nodes, parsers, prompt builder
  services/       orchestration (ingest, schema registry, review, qdrant, dlq)
  db/             async engine/session (RLS), ORM models, repositories
  worker/         per-tenant async worker pool + pipeline runner
  observability/  structured logging, PII masking, Prometheus metrics
migrations/       Alembic migrations (001 schema, 002 RLS, 003 audit triggers)
deploy/           Dockerfile, docker-compose, kubernetes manifests
tests/            unit + integration (RLS adversarial) suites
```
