"""Pipeline run execution metadata, and FASTQ verification bound to stored objects.

- pipeline_jobs: output dir, samplesheet URI, progress.
- fastq_files.verified_etag: the object version a verification applies to.
- Every existing verification is reset to ``pending``: the previous endpoint hashed the S3
  key and declared size, not the stored bytes, so those results prove nothing.
- FASTQ rows pointing outside their workspace storage namespace, or linked to a sample of
  another workspace, lose those links. Every reset is written to the audit trail.

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
    op.add_column("fastq_files", sa.Column("verified_etag", sa.String(length=128), nullable=True))
    _reset_fastq_verification()

    # Output rows seeded at launch before real execution existed (size 0, never produced).
    op.execute(
        "DELETE FROM run_output_files WHERE size_bytes = 0 AND md5 IS NULL "
        "AND s3_key LIKE '%/results/%' "
        "AND (s3_key LIKE '%/variants.vcf.gz' OR s3_key LIKE '%/aligned.bam' "
        "OR s3_key LIKE '%/multiqc_report.html')"
    )


def _reset_fastq_verification() -> None:
    # Audit first (append-only inserts are allowed), then change the rows.
    op.execute(
        """
        INSERT INTO audit_logs (id, action, entity_type, entity_id, workspace,
                                before_state, after_state, reason)
        SELECT gen_random_uuid(), 'verification_reset', 'fastq_file', f.id::text, f.workspace,
               jsonb_build_object('verificationStatus', f.verification_status::text,
                                  'computedMd5', f.computed_md5),
               jsonb_build_object('verificationStatus', 'pending'),
               'Migration 0005: checksum was not computed from the stored object'
        FROM fastq_files f WHERE f.verification_status <> 'pending'
        """
    )
    op.execute(
        "UPDATE fastq_files SET verification_status = 'pending', computed_md5 = NULL "
        "WHERE verification_status <> 'pending'"
    )
    op.execute(
        """
        INSERT INTO audit_logs (id, action, entity_type, entity_id, workspace,
                                before_state, after_state, reason)
        SELECT gen_random_uuid(), 'unlink_sample', 'fastq_file', f.id::text, f.workspace,
               jsonb_build_object('sampleId', f.sample_id::text),
               jsonb_build_object('sampleId', NULL),
               'Migration 0005: sample belongs to another workspace'
        FROM fastq_files f JOIN samples s ON s.id = f.sample_id
        WHERE s.workspace <> f.workspace
        """
    )
    op.execute(
        "UPDATE fastq_files f SET sample_id = NULL FROM samples s "
        "WHERE s.id = f.sample_id AND s.workspace <> f.workspace"
    )
    op.execute(
        """
        INSERT INTO audit_logs (id, action, entity_type, entity_id, workspace,
                                before_state, after_state, reason)
        SELECT gen_random_uuid(), 'quarantine', 'fastq_file', f.id::text, f.workspace,
               jsonb_build_object('s3Key', f.s3_key, 'sampleId', f.sample_id::text),
               jsonb_build_object('sampleId', NULL),
               'Migration 0005: object key outside the workspace storage namespace'
        FROM fastq_files f WHERE f.s3_key NOT LIKE f.workspace || '/fastq/%'
        """
    )
    op.execute(
        "UPDATE fastq_files SET sample_id = NULL WHERE s3_key NOT LIKE workspace || '/fastq/%'"
    )


def downgrade() -> None:
    op.drop_column("fastq_files", "verified_etag")
    op.drop_column("pipeline_jobs", "progress")
    op.drop_column("pipeline_jobs", "samplesheet_uri")
    op.drop_column("pipeline_jobs", "output_dir")
