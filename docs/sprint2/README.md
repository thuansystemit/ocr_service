# Sprint 2 — Auth, PII Encryption, Pipeline Foundation (Summary)

**Status:** ✅ Complete and verified in Docker (ruff + mypy + **37 tests** green against Postgres 16).
**Goal:** Auth complete · PII encrypted · LangGraph foundation (SP-001 resolved).

## What shipped

| Task | What | Where |
|------|------|-------|
| T-012 | SQLAlchemy 2.0 ORM models for all 11 tables; optimistic-lock (`version_id_col`) on `documents`/`review_tasks` | `app/db/models.py`, `app/db/base.py` |
| T-013 | Pydantic v2 request/response models (enums, tenant, schema-registry, document/extraction/guardrail/review) | `app/api/schemas/` |
| T-018 | **PII encryption** — AES-256-GCM, per-tenant HKDF-derived keys, tenant-id bound as GCM AAD, field-path encrypt/decrypt | `app/domain/encryption.py` |
| T-015 | **JWT RS256** verification (issuer/audience/expiry), tenant from signed claim | `app/services/auth.py` |
| T-016 | **API-key auth** — SHA-256 hash, 60s in-process TTL cache, revocation/expiry checks | `app/services/auth.py` |
| migration 004 | `auth_resolve_api_key` SECURITY DEFINER function (owned by `ocr_admin`, BYPASSRLS) for pre-tenant key lookup | `migrations/versions/004_auth_function.py` |
| T-017 | **Tenant context** — `ContextVar` + FastAPI deps wiring auth → tenant → RLS-scoped session; `/api/v1/me*` introspection | `app/api/context.py`, `app/api/dependencies.py`, `app/api/routers/me.py` |
| T-032 | `ExtractionState` TypedDict (all pipeline fields incl. `is_cancelled`) | `app/pipeline/state.py` |
| SP-001 | LangGraph checkpoint-postgres recovery spike — **resolved** | `docs/sdlc/SP-001-langgraph-checkpoint-recovery.md` |

## Verification

```
ruff check ........... All checks passed!
mypy ................. Success: no issues found in 31 source files
pytest ............... 37 passed
```

## Security design notes (worth a read before extending)

- **Cross-tenant key lookup without weakening RLS.** API-key auth must map a key
  to its tenant *before* any tenant context exists. Rather than give the app a
  broad `BYPASSRLS` login role, migration 004 exposes one narrow SECURITY DEFINER
  function owned by `ocr_admin`; `ocr_app` may only `EXECUTE` it. It returns just
  the columns auth needs — no arbitrary cross-tenant reads. See
  [docs/sprint2/AUTH.md](./AUTH.md).
- **PII encryption is defense-in-depth on top of RLS.** Each tenant gets its own
  AES key (HKDF from one master key), and the tenant id is bound in as GCM
  associated data, so a ciphertext from tenant A cannot be decrypted under tenant
  B even if rows were swapped. Verified by `tests/unit/test_encryption.py`.
- **Checkpoint recovery has one real gap.** LangGraph won't re-run *completed*
  nodes on resume, but a node that crashes *mid-flight* re-runs — so the EXTRACT
  node is made idempotent (skip the LLM call if output already present) and
  `extraction_results.document_id` is `UNIQUE`. See the SP-001 doc.

## What's still NOT possible after Sprint 2

No document processing yet — still no `POST /api/v1/extract`, no parsing, no
extraction pipeline graph (only its state shape and recovery design). Those are
**Sprint 3**. You can now authenticate and exercise tenant-scoped, RLS-enforced
endpoints (`/api/v1/me`, `/api/v1/me/schemas/count`).

## Testing

Same one-liner as Sprint 1:

```bash
docker compose -f deploy/docker-compose.yml --profile test run --build --rm test
```

See [docs/sprint2/AUTH.md](./AUTH.md) for how to mint an API key and call an
authenticated endpoint by hand.
