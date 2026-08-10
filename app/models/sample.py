"""Sample LIMS entity with multi-omics metadata."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OmicsModality(enum.StrEnum):
    genomics = "genomics"
    transcriptomics = "transcriptomics"
    epigenomics = "epigenomics"
    proteomics = "proteomics"
    metabolomics = "metabolomics"
    multiomics = "multiomics"


class QcStatus(enum.StrEnum):
    pending = "pending"
    pass_ = "pass"
    fail = "fail"
    warn = "warn"


class Sample(Base):
    __tablename__ = "samples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sample_code: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    workspace: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    patient_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    project_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    modality: Mapped[OmicsModality] = mapped_column(
        Enum(OmicsModality, name="omics_modality", native_enum=True),
        nullable=False,
    )
    tissue_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    collection_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rin_din: Mapped[float | None] = mapped_column(Float, nullable=True)
    concentration_ng_ul: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_ul: Mapped[float | None] = mapped_column(Float, nullable=True)
    qc_status: Mapped[QcStatus] = mapped_column(
        Enum(
            QcStatus,
            name="qc_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=QcStatus.pending,
    )
    qc_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
