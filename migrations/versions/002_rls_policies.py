"""row-level security: grants, enable+force RLS, tenant isolation policies

Revision ID: 002
Revises: 001
Create Date: 2026-06-11
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every tenant-scoped table (tenants is intentionally excluded: it is the root
# lookup table used during auth, before tenant context exists).
TENANT_TABLES: tuple[str, ...] = (
    "api_keys",
    "schemas",
    "schema_versions",
    "documents",
    "extraction_results",
    "guardrail_reports",
    "review_tasks",
    "audit_log",
    "dlq",
    "webhook_deliveries",
)


def upgrade() -> None:
    # -- Grants -------------------------------------------------------------
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ocr_app;")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ocr_app;")
    op.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO ocr_admin;")
    op.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO ocr_admin;")

    # -- Enable + FORCE RLS, then create the isolation policy per table -----
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY rls_{table} ON {table}
                FOR ALL
                TO ocr_app
                USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
                WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);
            """
        )


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS rls_{table} ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ocr_app;")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM ocr_app;")
