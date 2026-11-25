"""Pipeline run execution metadata: output dir, samplesheet URI, progress.

Revision ID: 0005_run_execution
Revises: 0004_sample_lims_fields
Create Date: 2026-11-25 17:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_run_execution"
down_revision: str | None = "0004_sample_lims_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pipeline_jobs", sa.Column("output_dir", sa.String(length=1024), nullable=True))
    op.add_column(
        "pipeline_jobs", sa.Column("samplesheet_uri", sa.String(length=1024), nullable=True)
    )
    op.add_column(
        "pipeline_jobs",
        sa.Column(
            "progress",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    # Output rows seeded at launch before real execution existed (size 0, never produced).
    op.execute(
        "DELETE FROM run_output_files WHERE size_bytes = 0 AND md5 IS NULL "
        "AND s3_key LIKE '%/results/%' "
        "AND (s3_key LIKE '%/variants.vcf.gz' OR s3_key LIKE '%/aligned.bam' "
        "OR s3_key LIKE '%/multiqc_report.html')"
    )


def downgrade() -> None:
    op.drop_column("pipeline_jobs", "progress")
    op.drop_column("pipeline_jobs", "samplesheet_uri")
    op.drop_column("pipeline_jobs", "output_dir")
