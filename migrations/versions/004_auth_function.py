"""auth_resolve_api_key: SECURITY DEFINER lookup that bypasses RLS safely

Revision ID: 004
Revises: 003
Create Date: 2026-06-12

API-key authentication must map an arbitrary key hash to its tenant *before* any
tenant context exists -- a chicken-and-egg with RLS on ``api_keys``. Rather than
hand the app a broad BYPASSRLS login role, we expose a single narrow function
owned by ``ocr_admin`` (which has BYPASSRLS). ``ocr_app`` may only EXECUTE it; it
returns just the columns auth needs and nothing else, so the app cannot run
arbitrary cross-tenant reads.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION auth_resolve_api_key(p_hash varchar)
        RETURNS TABLE (
            tenant_id   uuid,
            scopes      text[],
            expires_at  timestamptz,
            revoked_at  timestamptz
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT tenant_id, scopes, expires_at, revoked_at
            FROM api_keys
            WHERE key_hash = p_hash;
        $$;
        """
    )
    # Run the function body with ocr_admin's privileges (BYPASSRLS).
    op.execute("ALTER FUNCTION auth_resolve_api_key(varchar) OWNER TO ocr_admin;")
    # Least privilege: only ocr_app may call it.
    op.execute("REVOKE ALL ON FUNCTION auth_resolve_api_key(varchar) FROM PUBLIC;")
    op.execute("GRANT EXECUTE ON FUNCTION auth_resolve_api_key(varchar) TO ocr_app;")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS auth_resolve_api_key(varchar);")
