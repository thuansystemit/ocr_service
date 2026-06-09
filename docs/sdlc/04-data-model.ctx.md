---
doc: 04-data-model
agent: data-modeler
phase: 2
status: complete
human_doc: 04-data-model.md
source: [02-requirements, 03-architecture]
next: [java-developer, estimator, engineering]
provides:
  tables:
    - "tenants(id UUID PK, name VARCHAR NN, slug VARCHAR UK NN, webhook_url TEXT, webhook_secret TEXT NN, max_queue_size INT NN, retention_days INT NN, pii_to_llm_policy VARCHAR NN, config JSONB NN)"
    - "api_keys(id UUID PK, tenant_id UUID FK->tenants NN, key_hash VARCHAR UK NN, key_prefix VARCHAR NN, description TEXT, scopes TEXT[] NN, expires_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ)"
    - "schemas(id UUID PK, tenant_id UUID FK->tenants NN, name VARCHAR NN, json_schema JSONB NN, required_fields TEXT[] NN, pii_fields TEXT[] NN, prompt_template TEXT, status VARCHAR NN, current_version INT NN, confidence_high NUMERIC NN, confidence_medium NUMERIC NN, seed_count INT NN, config JSONB NN, UK(tenant_id,name))"
    - "schema_versions(id UUID PK, schema_id UUID FK->schemas NN, tenant_id UUID FK->tenants NN, version INT NN, json_schema JSONB NN, required_fields TEXT[] NN, pii_fields TEXT[] NN, prompt_template TEXT, UK(schema_id,version))"
    - "documents(id UUID PK, tenant_id UUID FK->tenants NN, schema_id UUID FK->schemas NN, schema_version INT NN, file_name VARCHAR, file_size_bytes BIGINT, mime_type VARCHAR, file_storage_key TEXT, status VARCHAR NN, confidence_overall NUMERIC, routing_decision VARCHAR, is_dry_run BOOL NN, pipeline_timeout_s INT NN, version INT NN)"
    - "extraction_results(id UUID PK, document_id UUID FK->documents UK NN, tenant_id UUID FK->tenants NN, extracted_json JSONB, extracted_json_hash VARCHAR, llm_model_used VARCHAR, llm_token_usage JSONB, confidence_overall NUMERIC, confidence_breakdown JSONB, low_confidence_fields TEXT[], missing_fields TEXT[])"
    - "guardrail_reports(id UUID PK, document_id UUID FK->documents NN, tenant_id UUID FK->tenants NN, guardrail_name VARCHAR NN, result VARCHAR NN, detail TEXT, confidence_multiplier NUMERIC NN)"
    - "review_tasks(id UUID PK, document_id UUID FK->documents UK NN, tenant_id UUID FK->tenants NN, extraction_result_id UUID FK->extraction_results NN, status VARCHAR NN, assigned_to UUID, reviewer_id UUID, corrections JSONB, rejection_reason TEXT, version INT NN)"
    - "audit_log(id UUID PK, tenant_id UUID NN, document_id UUID, event_type VARCHAR NN, actor VARCHAR, status VARCHAR, payload_hash VARCHAR, metadata JSONB -- NO FK, append-only via PG trigger)"
    - "dlq(id UUID PK, document_id UUID FK->documents NN, tenant_id UUID FK->tenants NN, failure_reason VARCHAR NN, pipeline_state JSONB, last_http_status INT, status VARCHAR NN, retry_count INT NN)"
    - "webhook_deliveries(id UUID PK, document_id UUID FK->documents NN, tenant_id UUID FK->tenants NN, attempt INT NN, http_status INT, response_body TEXT, error TEXT)"
  indexes: 24 total including PKs
  rls:
    enabled_tables: [api_keys, schemas, schema_versions, documents, extraction_results, guardrail_reports, review_tasks, audit_log, dlq, webhook_deliveries]
    excluded: [tenants]
    pattern: "USING (tenant_id = current_setting('app.current_tenant_id')::uuid)"
    session_var: "SET LOCAL app.current_tenant_id = '<uuid>'"
    bypass_role: ocr_admin (GDPR erasure + retention purge only)
  qdrant:
    collection: ocr_few_shot
    vector_dim: 1536
    distance: cosine
    payload: [tenant_id, schema_id, document_id, schema_name, source, input_text, expected_json, field_labels]
    isolation: "mandatory tenant_id filter + post-query assertion + prompt-builder verification"
  pydantic_models: [TenantBase, TenantResponse, SchemaBase, CreateSchemaRequest, SchemaResponse, SchemaVersionResponse, ExtractRequest, DocumentResponse, DocumentDetailResponse, ExtractionResultResponse, ConfidenceBreakdown, GuardrailReportResponse, ReviewTaskResponse, ReviewActionRequest, ExtractionState, ExtractionOutput]
  migrations:
    tool: alembic
    applied: none
    next: 001_initial_schema
    files: [001_initial_schema, 002_rls_policies, 003_audit_triggers]
constraints:
  - "PK: UUID gen_random_uuid()"
  - "Alembic only -- no ddl-auto"
  - "RLS on 10/11 tables (tenants excluded)"
  - "audit_log: append-only via PG trigger (trg_audit_no_update, trg_audit_no_delete)"
  - "schemas: activation gate trigger (seed_count >= 3)"
  - "optimistic locking: documents.version, review_tasks.version"
  - "PII: AES-256-GCM field-level in extracted_json JSONB"
  - "Qdrant: single collection, mandatory tenant_id filter"
open:
  - "DM-001: webhook_secret encryption at rest"
  - "DM-002: file_storage_key S3 vs local"
  - "DM-004: Qdrant vector dimension (1536 vs 768)"
  - "DM-005: audit_log PK UUID vs BIGSERIAL for ordering"
pull_hint: "full DDL, ERD, index rationale, RLS policies, Pydantic models, Qdrant design, migration plan -> 04-data-model.md"
---
