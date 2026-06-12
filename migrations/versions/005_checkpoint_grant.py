"""grant ocr_app CREATE on schema public for langgraph checkpoint tables

Revision ID: 005
Revises: 004
Create Date: 2026-06-12

``langgraph-checkpoint-postgres`` creates its own checkpoint tables on first
``saver.setup()``. Letting the app role create (and thus own) them is the
least-friction path: as owner, ``ocr_app`` has full DML on them without extra
default-privilege wiring. The checkpoint tables carry no tenant PII -- they are
keyed by ``thread_id = document_id`` and the app controls that key -- so they are
not RLS-scoped.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("GRANT CREATE ON SCHEMA public TO ocr_app;")


def downgrade() -> None:
    op.execute("REVOKE CREATE ON SCHEMA public FROM ocr_app;")
