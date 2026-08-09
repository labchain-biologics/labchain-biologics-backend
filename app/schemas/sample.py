"""Sample LIMS Pydantic schemas (camelCase frontend contract)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.sample import OmicsModality, QcStatus


class SampleBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sample_code: str = Field(alias="sampleCode", min_length=1, max_length=128)
    patient_id: str | None = Field(default=None, alias="patientId", max_length=128)
    project_code: str | None = Field(default=None, alias="projectCode", max_length=128)
    modality: OmicsModality
    tissue_type: str | None = Field(default=None, alias="tissueType", max_length=128)
    collection_date: str | None = Field(default=None, alias="collectionDate", max_length=32)
    rin_din: float | None = Field(default=None, alias="rinDin", ge=0, le=10)
    concentration_ng_ul: float | None = Field(
        default=None, alias="concentrationNgUl", ge=0
    )
    volume_ul: float | None = Field(default=None, alias="volumeUl", ge=0)
    qc_status: QcStatus = Field(default=QcStatus.pending, alias="qcStatus")
    qc_notes: str | None = Field(default=None, alias="qcNotes")
    metadata_json: dict[str, Any] = Field(default_factory=dict, alias="metadata")

    @field_validator("qc_status", mode="before")
    @classmethod
    def normalize_qc_status(cls, value: object) -> object:
        if value == "pass_":
            return "pass"
        return value


class SampleCreate(SampleBase):
    pass


class SampleUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sample_code: str | None = Field(default=None, alias="sampleCode", min_length=1, max_length=128)
    patient_id: str | None = Field(default=None, alias="patientId", max_length=128)
    project_code: str | None = Field(default=None, alias="projectCode", max_length=128)
    modality: OmicsModality | None = None
    tissue_type: str | None = Field(default=None, alias="tissueType", max_length=128)
    collection_date: str | None = Field(default=None, alias="collectionDate", max_length=32)
    rin_din: float | None = Field(default=None, alias="rinDin", ge=0, le=10)
    concentration_ng_ul: float | None = Field(
        default=None, alias="concentrationNgUl", ge=0
    )
    volume_ul: float | None = Field(default=None, alias="volumeUl", ge=0)
    qc_status: QcStatus | None = Field(default=None, alias="qcStatus")
    qc_notes: str | None = Field(default=None, alias="qcNotes")
    metadata_json: dict[str, Any] | None = Field(default=None, alias="metadata")


class SampleRead(SampleBase):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    workspace: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class SampleBulkPatchItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    patch: SampleUpdate


class SampleBulkPatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[SampleBulkPatchItem] = Field(min_length=1)


class SampleBulkDeleteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ids: list[uuid.UUID] = Field(min_length=1, alias="ids")


class SampleImportResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    created: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
    samples: list[SampleRead] = Field(default_factory=list)
