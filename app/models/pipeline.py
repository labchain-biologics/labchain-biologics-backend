"""Sequencing runs, FastQ files, pipeline jobs, and run outputs."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class JobStatus(enum.StrEnum):
    pending = "pending"
    submitted = "submitted"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class OutputFileType(enum.StrEnum):
    vcf = "vcf"
    bam = "bam"
    multiqc = "multiqc"
    other = "other"


class FastqVerificationStatus(enum.StrEnum):
    pending = "pending"
    verified = "verified"
    mismatch = "mismatch"


class SequencingRun(Base):
    __tablename__ = "sequencing_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_name: Mapped[str] = mapped_column(String(255), nullable=False)
    workspace: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    instrument: Mapped[str | None] = mapped_column(String(128), nullable=True)
    flowcell_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    fastq_files = relationship("FastqFile", back_populates="sequencing_run", lazy="selectin")
    pipeline_jobs = relationship("PipelineJob", back_populates="sequencing_run", lazy="selectin")


class FastqFile(Base):
    __tablename__ = "fastq_files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sequencing_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sequencing_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sample_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("samples.id", ondelete="SET NULL"), nullable=True
    )
    workspace: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    expected_md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    computed_md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verification_status: Mapped[FastqVerificationStatus] = mapped_column(
        Enum(FastqVerificationStatus, name="fastq_verification_status", native_enum=True),
        nullable=False,
        default=FastqVerificationStatus.pending,
    )
    read_pair: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sequencing_run = relationship("SequencingRun", back_populates="fastq_files")


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    pipeline_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    pipeline_name: Mapped[str] = mapped_column(String(255), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False, default="latest")
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", native_enum=True),
        nullable=False,
        default=JobStatus.pending,
        index=True,
    )
    sequencing_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sequencing_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    sample_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    aws_batch_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nextflow_run_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_dir: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    log_buffer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    launched_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sequencing_run = relationship("SequencingRun", back_populates="pipeline_jobs")
    output_files = relationship("RunOutputFile", back_populates="pipeline_job", lazy="selectin")


class RunOutputFile(Base):
    __tablename__ = "run_output_files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipeline_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    file_type: Mapped[OutputFileType] = mapped_column(
        Enum(OutputFileType, name="output_file_type", native_enum=True),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sample_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("samples.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    pipeline_job = relationship("PipelineJob", back_populates="output_files")
