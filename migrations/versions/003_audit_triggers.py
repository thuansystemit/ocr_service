"""audit_log immutability: block UPDATE/DELETE via triggers (REQ-037, D-011)

Revision ID: 003
Revises: 002
Create Date: 2026-06-11

The append-only guarantee is enforced in the database, not just the app. GDPR
erasure (the only legitimate delete) runs as the BYPASSRLS ``ocr_admin`` role,
which temporarily disables ``trg_audit_no_delete`` for the specific document and
then re-enables it -- see app/services/erasure.py (Sprint 6).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log records cannot be modified or deleted (immutability policy)';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_no_update
            BEFORE UPDATE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_no_delete
            BEFORE DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_no_delete ON audit_log;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_no_update ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_modification();")
