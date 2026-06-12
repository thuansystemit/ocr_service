# OCR Service

Enterprise OCR / document-extraction platform. Documents (PDF/image/DOCX) are
parsed with **LlamaParse**, run through a stateful **LangGraph** extraction
pipeline that calls an LLM via **LangChain** with tenant-scoped few-shot examples
retrieved from a **Qdrant** vector store, validated by a guardrail pipeline,
confidence-scored, and routed (auto-deliver / human review / dead-letter). Built
multi-tenant from the ground up (PostgreSQL Row-Level Security + Qdrant payload
isolation).

> Status: **Sprint 1 (foundation)** — project scaffold, config, structured
> logging, async DB layer with RLS, per-tenant worker pool, the full 11-table
> schema (migrations 001–003), Docker/K8s skeletons, and the RLS adversarial
> test suite. Pipeline, parsing, extraction, and review land in later sprints.

The full SDLC design lives under [`docs/sdlc/`](docs/sdlc/): product spec,
requirements, architecture, data model, estimation, and the sprint plan.

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
