# Sprint 2 — Authenticating & Testing the API

After Sprint 2 the API has two credential types and tenant-scoped (RLS) access.
This guide shows how to mint an API key and call an authenticated endpoint.

## Credential types

| Type | Header | Tenant source | Notes |
|------|--------|---------------|-------|
| **API key** | `Authorization: Bearer ocr_<token>` | DB lookup (hashed) | SHA-256 hashed; 60s cache; revocable/expirable |
| **JWT (RS256)** | `Authorization: Bearer <jwt>` | signed `tenant_id` claim | needs `OCR_JWT_PUBLIC_KEY_PATH`; no DB hit |

## Mint an API key (dev)

Keys are SHA-256 hashed before storage; the raw key is shown once. Use the
in-image Python helper to generate the parts, then insert the tenant + key.

```bash
# Bring the stack up (postgres + migrations applied)
make up

# 1) Generate a key + its hash/prefix
docker compose -f deploy/docker-compose.yml exec api \
  python -c "from app.services.auth import generate_api_key; r,p,h=generate_api_key(); print('RAW =',r); print('PREFIX =',p); print('HASH =',h)"
```

```bash
# 2) Insert a tenant and the api_key row (RLS is satisfied by SET LOCAL).
#    Replace <HASH>/<PREFIX> with the values printed above.
docker compose -f deploy/docker-compose.yml exec postgres \
  psql -U postgres -d ocr -v ON_ERROR_STOP=1 <<'SQL'
\set tenant '11111111-1111-1111-1111-111111111111'
SET LOCAL app.current_tenant_id = :'tenant';
INSERT INTO tenants (id, name, slug, webhook_secret)
  VALUES (:'tenant', 'Acme', 'acme', 'dev-webhook-secret')
  ON CONFLICT (id) DO NOTHING;
INSERT INTO api_keys (tenant_id, key_hash, key_prefix)
  VALUES (:'tenant', '<HASH>', '<PREFIX>');
SQL
```

> `psql` runs as the `postgres` superuser here, which bypasses RLS, so the
> `SET LOCAL` is belt-and-suspenders. In application code the `ocr_app` role
> requires it.

## Call an authenticated endpoint

```bash
RAW=ocr_xxxxxxxx...   # the RAW value from step 1

curl -s localhost:8000/api/v1/me \
  -H "Authorization: Bearer $RAW"
# {"tenant_id":"1111...","principal":"apikey:xxxxxxxx","scopes":["extract","read"]}

curl -s localhost:8000/api/v1/me/schemas/count \
  -H "Authorization: Bearer $RAW"
# {"tenant_id":"1111...","schema_count":0}   # RLS-scoped to this tenant

curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/api/v1/me
# 401  (no Authorization header)
```

## Verifying tenant isolation yourself

Create a **second** tenant + key, insert a `schemas` row for each, then call
`/api/v1/me/schemas/count` with each key — each sees only its own count. This is
exactly what `tests/integration/test_auth_flow.py::test_rls_scopes_query_to_caller_tenant`
asserts automatically.

## JWT auth (optional)

1. Generate an RS256 keypair; mount the **public** key at the path in
   `OCR_JWT_PUBLIC_KEY_PATH` (default `./deploy/keys/jwt_public.pem`).
2. Issue a JWT signed with the private key, including claims:
   `iss=ocr-platform`, `aud=ocr-api`, `tenant_id=<uuid>`, `scopes=[...]`, `exp`.
3. Send it as `Authorization: Bearer <jwt>`. No DB lookup occurs — the tenant is
   read from the verified claim.

See `tests/unit/test_auth.py` for a complete keypair-sign-verify example.
