"""Sample LIMS fields, server-managed sample status, sequencing run read length.

Adds the LIMS metadata the web client needs (assay, sample type, platform, library prep, ...),
a lifecycle ``status`` maintained by the server, ``created_by``, and a per-workspace unique
sample code. The migration fails with a clear message if duplicate sample codes already exist
in a workspace; resolve them first.

Revision ID: 0004_sample_lims_fields
Revises: 0003_workspaces
Create Date: 2026-11-25 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_sample_lims_fields"
down_revision: str | None = "0003_workspaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

sample_assay = postgresql.ENUM(
    "wgs",
    "exome",
    "targeted_panel",
    "bulk_rna",
    "single_cell_rna",
    "atac_seq",
    "methylation",
    "amplicon_16s",
    "metagenomics",
    name="sample_assay",
    create_type=False,
)
sample_type = postgresql.ENUM(
    "tumor",
    "normal",
    "control",
    "environmental",
    "cell_line",
    name="sample_type",
    create_type=False,
)
sample_status = postgresql.ENUM(
    "registered",
    "fastq_received",
    "processing",
    "completed",
    name="sample_status",
    create_type=False,
)

STRING_COLUMNS: tuple[tuple[str, int], ...] = (
    ("organism", 128),
    ("biobank_id", 128),
    ("paired_group", 128),
    ("platform", 255),
    ("library_prep_kit", 255),
    ("target_panel", 255),
    ("index_id", 128),
)


def upgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT workspace, sample_code, count(*) FROM samples "
            "GROUP BY workspace, sample_code HAVING count(*) > 1 LIMIT 10"
        )
    ).fetchall()
    if duplicates:
        listed = ", ".join(f"{row[0]}/{row[1]} (x{row[2]})" for row in duplicates)
        raise RuntimeError(
            "Cannot add unique (workspace, sample_code): duplicate sample codes exist: " + listed
        )

    for enum_type in (sample_assay, sample_type, sample_status):
        enum_type.create(bind, checkfirst=True)

    op.add_column("samples", sa.Column("assay", sample_assay, nullable=True))
    op.add_column("samples", sa.Column("sample_type", sample_type, nullable=True))
    op.add_column(
        "samples",
        sa.Column("status", sample_status, nullable=False, server_default="registered"),
    )
    op.alter_column("samples", "status", server_default=None)
    for name, length in STRING_COLUMNS:
        op.add_column("samples", sa.Column(name, sa.String(length=length), nullable=True))
    op.add_column("samples", sa.Column("a260_280", sa.Float(), nullable=True))
    op.add_column("samples", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "samples",
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_samples_created_by"),
            nullable=True,
        ),
    )
    op.create_index("ix_samples_status", "samples", ["status"])
    op.create_unique_constraint(
        "uq_samples_workspace_code", "samples", ["workspace", "sample_code"]
    )

    op.add_column("sequencing_runs", sa.Column("read_length", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("sequencing_runs", "read_length")

    op.drop_constraint("uq_samples_workspace_code", "samples", type_="unique")
    op.drop_index("ix_samples_status", table_name="samples")
    op.drop_constraint("fk_samples_created_by", "samples", type_="foreignkey")
    for column in ("created_by", "notes", "a260_280", "status", "sample_type", "assay"):
        op.drop_column("samples", column)
    for name, _length in STRING_COLUMNS:
        op.drop_column("samples", name)

    bind = op.get_bind()
    for enum_type in (sample_status, sample_type, sample_assay):
        enum_type.drop(bind, checkfirst=True)
