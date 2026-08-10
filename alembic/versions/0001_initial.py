"""Initial LabChain schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-09 18:57:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# create_type=False: enums are created explicitly in upgrade(); otherwise
# create_table would emit CREATE TYPE again and fail with DuplicateObjectError.
user_role = postgresql.ENUM(
    "bioinformatics_lead",
    "lab_technician",
    name="user_role",
    create_type=False,
)
omics_modality = postgresql.ENUM(
    "genomics",
    "transcriptomics",
    "epigenomics",
    "proteomics",
    "metabolomics",
    "multiomics",
    name="omics_modality",
    create_type=False,
)
qc_status = postgresql.ENUM(
    "pending",
    "pass",
    "fail",
    "warn",
    name="qc_status",
    create_type=False,
)
job_status = postgresql.ENUM(
    "pending",
    "submitted",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    name="job_status",
    create_type=False,
)
output_file_type = postgresql.ENUM(
    "vcf",
    "bam",
    "multiqc",
    "other",
    name="output_file_type",
    create_type=False,
)
fastq_verification_status = postgresql.ENUM(
    "pending",
    "verified",
    "mismatch",
    name="fastq_verification_status",
    create_type=False,
)


def upgrade() -> None:
    user_role.create(op.get_bind(), checkfirst=True)
    omics_modality.create(op.get_bind(), checkfirst=True)
    qc_status.create(op.get_bind(), checkfirst=True)
    job_status.create(op.get_bind(), checkfirst=True)
    output_file_type.create(op.get_bind(), checkfirst=True)
    fastq_verification_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("google_sub", sa.String(length=255), nullable=True),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("google_sub"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "samples",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("sample_code", sa.String(length=128), nullable=False),
        sa.Column("workspace", sa.String(length=128), nullable=False),
        sa.Column("patient_id", sa.String(length=128), nullable=True),
        sa.Column("project_code", sa.String(length=128), nullable=True),
        sa.Column("modality", omics_modality, nullable=False),
        sa.Column("tissue_type", sa.String(length=128), nullable=True),
        sa.Column("collection_date", sa.String(length=32), nullable=True),
        sa.Column("rin_din", sa.Float(), nullable=True),
        sa.Column("concentration_ng_ul", sa.Float(), nullable=True),
        sa.Column("volume_ul", sa.Float(), nullable=True),
        sa.Column("qc_status", qc_status, nullable=False),
        sa.Column("qc_notes", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_samples_sample_code", "samples", ["sample_code"])
    op.create_index("ix_samples_workspace", "samples", ["workspace"])

    op.create_table(
        "sequencing_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_name", sa.String(length=255), nullable=False),
        sa.Column("workspace", sa.String(length=128), nullable=False),
        sa.Column("instrument", sa.String(length=128), nullable=True),
        sa.Column("flowcell_id", sa.String(length=128), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_sequencing_runs_workspace", "sequencing_runs", ["workspace"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("workspace", sa.String(length=128), nullable=False),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_workspace", "audit_logs", ["workspace"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "fastq_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("sequencing_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sample_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workspace", sa.String(length=128), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("s3_key", sa.String(length=1024), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("expected_md5", sa.String(length=32), nullable=True),
        sa.Column("computed_md5", sa.String(length=32), nullable=True),
        sa.Column("verification_status", fastq_verification_status, nullable=False),
        sa.Column("read_pair", sa.String(length=8), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["sequencing_run_id"], ["sequencing_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sample_id"], ["samples.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_fastq_files_workspace", "fastq_files", ["workspace"])
    op.create_index("ix_fastq_files_sequencing_run_id", "fastq_files", ["sequencing_run_id"])

    op.create_table(
        "pipeline_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace", sa.String(length=128), nullable=False),
        sa.Column("pipeline_id", sa.String(length=128), nullable=False),
        sa.Column("pipeline_name", sa.String(length=255), nullable=False),
        sa.Column(
            "pipeline_version",
            sa.String(length=64),
            nullable=False,
            server_default="latest",
        ),
        sa.Column("status", job_status, nullable=False),
        sa.Column("sequencing_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "sample_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("aws_batch_job_id", sa.String(length=255), nullable=True),
        sa.Column("nextflow_run_name", sa.String(length=255), nullable=True),
        sa.Column("work_dir", sa.String(length=1024), nullable=True),
        sa.Column("log_buffer", sa.Text(), nullable=False, server_default=""),
        sa.Column("launched_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["sequencing_run_id"], ["sequencing_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["launched_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_pipeline_jobs_workspace", "pipeline_jobs", ["workspace"])
    op.create_index("ix_pipeline_jobs_pipeline_id", "pipeline_jobs", ["pipeline_id"])
    op.create_index("ix_pipeline_jobs_status", "pipeline_jobs", ["status"])

    op.create_table(
        "run_output_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("pipeline_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace", sa.String(length=128), nullable=False),
        sa.Column("file_type", output_file_type, nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("s3_key", sa.String(length=1024), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("md5", sa.String(length=32), nullable=True),
        sa.Column("sample_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["pipeline_job_id"], ["pipeline_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sample_id"], ["samples.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_run_output_files_workspace", "run_output_files", ["workspace"])
    op.create_index("ix_run_output_files_pipeline_job_id", "run_output_files", ["pipeline_job_id"])


def downgrade() -> None:
    op.drop_index("ix_run_output_files_pipeline_job_id", table_name="run_output_files")
    op.drop_index("ix_run_output_files_workspace", table_name="run_output_files")
    op.drop_table("run_output_files")

    op.drop_index("ix_pipeline_jobs_status", table_name="pipeline_jobs")
    op.drop_index("ix_pipeline_jobs_pipeline_id", table_name="pipeline_jobs")
    op.drop_index("ix_pipeline_jobs_workspace", table_name="pipeline_jobs")
    op.drop_table("pipeline_jobs")

    op.drop_index("ix_fastq_files_sequencing_run_id", table_name="fastq_files")
    op.drop_index("ix_fastq_files_workspace", table_name="fastq_files")
    op.drop_table("fastq_files")

    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_workspace", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_sequencing_runs_workspace", table_name="sequencing_runs")
    op.drop_table("sequencing_runs")

    op.drop_index("ix_samples_workspace", table_name="samples")
    op.drop_index("ix_samples_sample_code", table_name="samples")
    op.drop_table("samples")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    fastq_verification_status.drop(op.get_bind(), checkfirst=True)
    output_file_type.drop(op.get_bind(), checkfirst=True)
    job_status.drop(op.get_bind(), checkfirst=True)
    qc_status.drop(op.get_bind(), checkfirst=True)
    omics_modality.drop(op.get_bind(), checkfirst=True)
    user_role.drop(op.get_bind(), checkfirst=True)
