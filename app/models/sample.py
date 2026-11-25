"""Sample LIMS entity with multi-omics metadata."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, utc_now


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [str(member.value) for member in enum_cls]


class OmicsModality(enum.StrEnum):
    """Broad omics family of a sample."""

    genomics = "genomics"
    transcriptomics = "transcriptomics"
    epigenomics = "epigenomics"
    proteomics = "proteomics"
    metabolomics = "metabolomics"
    multiomics = "multiomics"


class SampleAssay(enum.StrEnum):
    """Sequencing assay the sample is prepared for. Drives the suggested pipeline."""

    wgs = "wgs"
    exome = "exome"
    targeted_panel = "targeted_panel"
    bulk_rna = "bulk_rna"
    single_cell_rna = "single_cell_rna"
    atac_seq = "atac_seq"
    methylation = "methylation"
    amplicon_16s = "amplicon_16s"
    metagenomics = "metagenomics"


class SampleType(enum.StrEnum):
    tumor = "tumor"
    normal = "normal"
    control = "control"
    environmental = "environmental"
    cell_line = "cell_line"


class SampleStatus(enum.StrEnum):
    """Lifecycle status, maintained by the server (never set directly by clients)."""

    registered = "registered"
    fastq_received = "fastq_received"
    processing = "processing"
    completed = "completed"


class QcStatus(enum.StrEnum):
    pending = "pending"
    pass_ = "pass"
    fail = "fail"
    warn = "warn"


class Sample(Base):
    __tablename__ = "samples"
    __table_args__ = (
        UniqueConstraint("workspace", "sample_code", name="uq_samples_workspace_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sample_code: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    workspace: Mapped[str] = mapped_column(
        String(128), ForeignKey("workspaces.slug"), index=True, nullable=False
    )
    patient_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    project_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    modality: Mapped[OmicsModality] = mapped_column(
        Enum(OmicsModality, name="omics_modality", native_enum=True),
        nullable=False,
    )
    assay: Mapped[SampleAssay | None] = mapped_column(
        Enum(SampleAssay, name="sample_assay", native_enum=True, values_callable=_enum_values),
        nullable=True,
    )
    sample_type: Mapped[SampleType | None] = mapped_column(
        Enum(SampleType, name="sample_type", native_enum=True, values_callable=_enum_values),
        nullable=True,
    )
    status: Mapped[SampleStatus] = mapped_column(
        Enum(SampleStatus, name="sample_status", native_enum=True, values_callable=_enum_values),
        nullable=False,
        default=SampleStatus.registered,
        index=True,
    )
    tissue_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    organism: Mapped[str | None] = mapped_column(String(128), nullable=True)
    collection_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    biobank_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    paired_group: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(255), nullable=True)
    library_prep_kit: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_panel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    index_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rin_din: Mapped[float | None] = mapped_column(Float, nullable=True)
    concentration_ng_ul: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_ul: Mapped[float | None] = mapped_column(Float, nullable=True)
    a260_280: Mapped[float | None] = mapped_column(Float, nullable=True)
    qc_status: Mapped[QcStatus] = mapped_column(
        Enum(QcStatus, name="qc_status", native_enum=True, values_callable=_enum_values),
        nullable=False,
        default=QcStatus.pending,
    )
    qc_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=utc_now,
        nullable=False,
    )
