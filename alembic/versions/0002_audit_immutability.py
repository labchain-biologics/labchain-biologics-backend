"""Enforce audit log immutability at DB level.

Revision ID: 0002_audit_immutability
Revises: 0001_initial
Create Date: 2026-08-10 14:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_audit_immutability"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_logs_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only: % operations are not allowed', TG_OP
                USING ERRCODE = '42501';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_prevent_audit_logs_update
        BEFORE UPDATE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_logs_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_prevent_audit_logs_delete
        BEFORE DELETE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_logs_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_prevent_audit_logs_delete ON audit_logs;")
    op.execute("DROP TRIGGER IF EXISTS trg_prevent_audit_logs_update ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_logs_mutation();")
