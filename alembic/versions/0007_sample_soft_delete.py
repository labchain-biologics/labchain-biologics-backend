"""Soft delete for samples.

Deleting a sample used to remove its row, which also cleared ``sample_id`` on its FASTQ files
and run outputs (``ON DELETE SET NULL``). Regulated records are now kept: deletion sets
``deleted_at`` and is audited. Sample codes of deleted samples stay reserved (the unique
constraint is unchanged).

Revision ID: 0007_sample_soft_delete
Revises: 0006_api_tokens
Create Date: 2026-11-25 20:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_sample_soft_delete"
down_revision: str | None = "0006_api_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("samples", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Dropping the column would resurrect soft-deleted samples. Refuse while any exist.
    bind = op.get_bind()
    deleted = bind.execute(
        sa.text("SELECT count(*) FROM samples WHERE deleted_at IS NOT NULL")
    ).scalar_one()
    if deleted:
        raise RuntimeError(
            f"{deleted} soft-deleted sample(s) exist; downgrading would make them visible again"
        )
    op.drop_column("samples", "deleted_at")
