"""initial schema: extensions, roles, functions, 11 tables, indexes, triggers

Revision ID: 001
Revises:
Create Date: 2026-06-11
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- Extensions ---------------------------------------------------------
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm";')

    # -- Roles (idempotent) -------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ocr_app') THEN
                CREATE ROLE ocr_app LOGIN PASSWORD 'changeme_in_production';
            END IF;
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ocr_admin') THEN
                CREATE ROLE ocr_admin NOLOGIN BYPASSRLS;
            END IF;
        END
        $$;
        """
    )

    # -- Utility functions --------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trigger_set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION check_schema_activation()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.status = 'active' AND NEW.seed_count < 3 THEN
                RAISE EXCEPTION 'Schema activation requires at least 3 seed examples (has %)', NEW.seed_count;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # -- tenants ------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE tenants (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name                VARCHAR(255) NOT NULL,
            slug                VARCHAR(63) NOT NULL UNIQUE,
            webhook_url         TEXT,
            webhook_secret      TEXT NOT NULL,
            max_queue_size      INT NOT NULL DEFAULT 500
                                    CHECK (max_queue_size > 0 AND max_queue_size <= 10000),
            retention_days      INT NOT NULL DEFAULT 90
                                    CHECK (retention_days >= 1 AND retention_days <= 3650),
            pii_to_llm_policy   VARCHAR(30) NOT NULL DEFAULT 'ENCRYPT_BEFORE_LLM'
                                    CHECK (pii_to_llm_policy IN (
                                        'ENCRYPT_BEFORE_LLM','REDACT_BEFORE_LLM','ALLOW_PLAINTEXT')),
            config              JSONB NOT NULL DEFAULT '{}',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TRIGGER trg_tenants_updated_at
            BEFORE UPDATE ON tenants
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
        """
    )

    # -- api_keys -----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE api_keys (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            key_hash            VARCHAR(128) NOT NULL,
            key_prefix          VARCHAR(8) NOT NULL,
            description         TEXT,
            scopes              TEXT[] NOT NULL DEFAULT '{extract,read}',
            expires_at          TIMESTAMPTZ,
            revoked_at          TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE UNIQUE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
        CREATE INDEX idx_api_keys_tenant_id ON api_keys(tenant_id);
        """
    )

    # -- schemas ------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE schemas (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name                VARCHAR(255) NOT NULL,
            description         TEXT,
            json_schema         JSONB NOT NULL,
            required_fields     TEXT[] NOT NULL DEFAULT '{}',
            pii_fields          TEXT[] NOT NULL DEFAULT '{}',
            prompt_template     TEXT,
            status              VARCHAR(20) NOT NULL DEFAULT 'draft'
                                    CHECK (status IN ('draft','active','deprecated')),
            current_version     INT NOT NULL DEFAULT 1 CHECK (current_version >= 1),
            confidence_high     NUMERIC(4,3) NOT NULL DEFAULT 0.850
                                    CHECK (confidence_high > confidence_medium AND confidence_high <= 1.0),
            confidence_medium   NUMERIC(4,3) NOT NULL DEFAULT 0.600
                                    CHECK (confidence_medium >= 0.0 AND confidence_medium < confidence_high),
            seed_count          INT NOT NULL DEFAULT 0 CHECK (seed_count >= 0),
            config              JSONB NOT NULL DEFAULT '{}',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_schemas_tenant_name UNIQUE (tenant_id, name)
        );
        CREATE INDEX idx_schemas_tenant_id ON schemas(tenant_id);
        CREATE INDEX idx_schemas_tenant_status ON schemas(tenant_id, status);
        CREATE TRIGGER trg_schemas_updated_at
            BEFORE UPDATE ON schemas
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
        CREATE TRIGGER trg_schema_activation_gate
            BEFORE INSERT OR UPDATE ON schemas
            FOR EACH ROW EXECUTE FUNCTION check_schema_activation();
        """
    )

    # -- schema_versions ----------------------------------------------------
    op.execute(
        """
        CREATE TABLE schema_versions (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            schema_id           UUID NOT NULL REFERENCES schemas(id) ON DELETE CASCADE,
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            version             INT NOT NULL CHECK (version >= 1),
            json_schema         JSONB NOT NULL,
            required_fields     TEXT[] NOT NULL,
            pii_fields          TEXT[] NOT NULL,
            prompt_template     TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_schema_versions_schema_version UNIQUE (schema_id, version)
        );
        CREATE INDEX idx_schema_versions_schema_id ON schema_versions(schema_id);
        CREATE INDEX idx_schema_versions_tenant_id ON schema_versions(tenant_id);
        """
    )

    # -- documents ----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE documents (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            schema_id           UUID NOT NULL REFERENCES schemas(id),
            schema_version      INT NOT NULL,
            file_name           VARCHAR(512),
            file_size_bytes     BIGINT CHECK (file_size_bytes >= 0),
            mime_type           VARCHAR(100),
            file_storage_key    TEXT,
            status              VARCHAR(30) NOT NULL DEFAULT 'pending'
                                    CHECK (status IN (
                                        'pending','parsing','guarding','extracting',
                                        'scoring','routing','delivering',
                                        'completed','review','rejected','error',
                                        'cancelled','tombstone')),
            confidence_overall  NUMERIC(4,3) CHECK (confidence_overall >= 0 AND confidence_overall <= 1.0),
            routing_decision    VARCHAR(10) CHECK (routing_decision IN ('HIGH','MEDIUM','LOW')),
            is_dry_run          BOOLEAN NOT NULL DEFAULT false,
            pipeline_timeout_s  INT NOT NULL DEFAULT 60
                                    CHECK (pipeline_timeout_s >= 5 AND pipeline_timeout_s <= 600),
            version             INT NOT NULL DEFAULT 1,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_documents_tenant_status ON documents(tenant_id, status);
        CREATE INDEX idx_documents_tenant_created ON documents(tenant_id, created_at);
        CREATE INDEX idx_documents_retention_purge ON documents(tenant_id, created_at)
            WHERE status NOT IN ('tombstone','cancelled');
        CREATE INDEX idx_documents_pending_recovery ON documents(status, created_at)
            WHERE status IN ('pending','parsing','guarding','extracting','scoring','routing','delivering');
        CREATE TRIGGER trg_documents_updated_at
            BEFORE UPDATE ON documents
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
        """
    )

    # -- extraction_results -------------------------------------------------
    op.execute(
        """
        CREATE TABLE extraction_results (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id             UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            extracted_json          JSONB,
            extracted_json_hash     VARCHAR(64),
            llm_model_used          VARCHAR(100),
            llm_token_usage         JSONB,
            confidence_overall      NUMERIC(4,3),
            confidence_breakdown    JSONB,
            low_confidence_fields   TEXT[],
            missing_fields          TEXT[],
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE UNIQUE INDEX idx_extraction_results_document_id ON extraction_results(document_id);
        CREATE INDEX idx_extraction_results_tenant_id ON extraction_results(tenant_id);
        """
    )

    # -- guardrail_reports --------------------------------------------------
    op.execute(
        """
        CREATE TABLE guardrail_reports (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id             UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            guardrail_name          VARCHAR(100) NOT NULL,
            result                  VARCHAR(10) NOT NULL CHECK (result IN ('pass','warn','block')),
            detail                  TEXT,
            confidence_multiplier   NUMERIC(4,3) NOT NULL DEFAULT 1.000
                                        CHECK (confidence_multiplier > 0 AND confidence_multiplier <= 1.0),
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_guardrail_reports_document_id ON guardrail_reports(document_id);
        CREATE INDEX idx_guardrail_reports_tenant_id ON guardrail_reports(tenant_id);
        """
    )

    # -- review_tasks -------------------------------------------------------
    op.execute(
        """
        CREATE TABLE review_tasks (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id             UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            extraction_result_id    UUID NOT NULL REFERENCES extraction_results(id) ON DELETE CASCADE,
            status                  VARCHAR(20) NOT NULL DEFAULT 'pending'
                                        CHECK (status IN ('pending','in_progress','accepted','corrected','rejected')),
            assigned_to             UUID,
            reviewer_id             UUID,
            corrections             JSONB,
            rejection_reason        TEXT,
            version                 INT NOT NULL DEFAULT 1,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_review_tasks_tenant_status ON review_tasks(tenant_id, status);
        CREATE INDEX idx_review_tasks_stale ON review_tasks(created_at)
            WHERE status IN ('pending','in_progress');
        CREATE UNIQUE INDEX idx_review_tasks_document_id ON review_tasks(document_id);
        CREATE TRIGGER trg_review_tasks_updated_at
            BEFORE UPDATE ON review_tasks
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
        """
    )

    # -- audit_log (no FKs by design) --------------------------------------
    op.execute(
        """
        CREATE TABLE audit_log (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL,
            document_id         UUID,
            event_type          VARCHAR(50) NOT NULL,
            actor               VARCHAR(255),
            status              VARCHAR(30),
            payload_hash        VARCHAR(64),
            metadata            JSONB,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_audit_log_tenant_created ON audit_log(tenant_id, created_at);
        CREATE INDEX idx_audit_log_document_id ON audit_log(document_id) WHERE document_id IS NOT NULL;
        CREATE INDEX idx_audit_log_event_type ON audit_log(tenant_id, event_type);
        """
    )

    # -- dlq ----------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE dlq (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id         UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            failure_reason      VARCHAR(100) NOT NULL CHECK (failure_reason IN (
                                    'PARSE_FAILED','PARSE_EMPTY_OUTPUT','GUARDRAIL_BLOCK',
                                    'INJECTION_DETECTED','LLM_UNAVAILABLE','EXTRACTION_FAILED',
                                    'LOW_CONFIDENCE','PIPELINE_TIMEOUT','WEBHOOK_DELIVERY_FAILED','UNKNOWN')),
            pipeline_state      JSONB,
            last_http_status    INT,
            status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending','retrying','resolved','expired')),
            retry_count         INT NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_dlq_tenant_status ON dlq(tenant_id, status);
        CREATE INDEX idx_dlq_document_id ON dlq(document_id);
        CREATE TRIGGER trg_dlq_updated_at
            BEFORE UPDATE ON dlq
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
        """
    )

    # -- webhook_deliveries -------------------------------------------------
    op.execute(
        """
        CREATE TABLE webhook_deliveries (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id         UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            attempt             INT NOT NULL CHECK (attempt >= 1 AND attempt <= 10),
            http_status         INT,
            response_body       TEXT,
            error               TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_webhook_deliveries_document_id ON webhook_deliveries(document_id);
        CREATE INDEX idx_webhook_deliveries_tenant_id ON webhook_deliveries(tenant_id);
        """
    )


def downgrade() -> None:
    for table in (
        "webhook_deliveries",
        "dlq",
        "audit_log",
        "review_tasks",
        "guardrail_reports",
        "extraction_results",
        "documents",
        "schema_versions",
        "schemas",
        "api_keys",
        "tenants",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")

    op.execute("DROP FUNCTION IF EXISTS check_schema_activation();")
    op.execute("DROP FUNCTION IF EXISTS trigger_set_updated_at();")
    # Roles and extensions are intentionally left in place; they may be shared.
