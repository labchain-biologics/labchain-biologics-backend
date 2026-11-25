"""Sample LIMS Pydantic schemas (camelCase frontend contract)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.models.sample import OmicsModality, QcStatus, SampleAssay, SampleStatus, SampleType

# Requests use `metadata`. Reading from the ORM must try `metadata_json` first, because
# `Sample.metadata` is SQLAlchemy's reserved MetaData object.
_METADATA_INPUT_ALIASES = AliasChoices("metadata", "metadata_json")
_METADATA_ORM_ALIASES = AliasChoices("metadata_json", "metadata")


def _normalize_qc_status(value: object) -> object:
    return "pass" if value == "pass_" else value


class SampleFields(BaseModel):
    """Client-editable sample fields. ``status`` and ``createdBy`` are server-managed."""

    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    patient_id: str | None = Field(default=None, alias="patientId", max_length=128)
    project_code: str | None = Field(default=None, alias="projectCode", max_length=128)
    assay: SampleAssay | None = None
    sample_type: SampleType | None = Field(default=None, alias="sampleType")
    tissue_type: str | None = Field(default=None, alias="tissueType", max_length=128)
    organism: str | None = Field(default=None, max_length=128)
    collection_date: str | None = Field(default=None, alias="collectionDate", max_length=32)
    biobank_id: str | None = Field(default=None, alias="biobankId", max_length=128)
    paired_group: str | None = Field(default=None, alias="pairedGroup", max_length=128)
    platform: str | None = Field(default=None, max_length=255)
    library_prep_kit: str | None = Field(default=None, alias="libraryPrepKit", max_length=255)
    target_panel: str | None = Field(default=None, alias="targetPanel", max_length=255)
    index_id: str | None = Field(default=None, alias="indexId", max_length=128)
    rin_din: float | None = Field(default=None, alias="rinDin", ge=0, le=10)
    concentration_ng_ul: float | None = Field(default=None, alias="concentrationNgUl", ge=0)
    volume_ul: float | None = Field(default=None, alias="volumeUl", ge=0)
    a260_280: float | None = Field(default=None, alias="a260280", ge=0, le=5)
    qc_notes: str | None = Field(default=None, alias="qcNotes")
    notes: str | None = None


class SampleBase(SampleFields):
    sample_code: str = Field(alias="sampleCode", min_length=1, max_length=128)
    modality: OmicsModality
    qc_status: QcStatus = Field(default=QcStatus.pending, alias="qcStatus")
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=_METADATA_INPUT_ALIASES,
        serialization_alias="metadata",
    )

    @field_validator("qc_status", mode="before")
    @classmethod
    def normalize_qc_status(cls, value: object) -> object:
        return _normalize_qc_status(value)


class SampleCreate(SampleBase):
    pass


class SampleUpdate(SampleFields):
    """Partial update: only fields present in the request body are applied."""

    sample_code: str | None = Field(default=None, alias="sampleCode", min_length=1, max_length=128)
    modality: OmicsModality | None = None
    qc_status: QcStatus | None = Field(default=None, alias="qcStatus")
    metadata_json: dict[str, Any] | None = Field(
        default=None,
        validation_alias=_METADATA_INPUT_ALIASES,
        serialization_alias="metadata",
    )

    @field_validator("qc_status", mode="before")
    @classmethod
    def normalize_qc_status(cls, value: object) -> object:
        return _normalize_qc_status(value)


class SampleRead(SampleBase):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True,
        populate_by_name=True,
        from_attributes=True,
    )

    id: uuid.UUID
    workspace: str
    status: SampleStatus
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=_METADATA_ORM_ALIASES,
        serialization_alias="metadata",
    )
    created_by: uuid.UUID | None = Field(default=None, alias="createdBy")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class SampleBulkPatchItem(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    id: uuid.UUID
    patch: SampleUpdate


class SampleBulkPatchRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    items: list[SampleBulkPatchItem] = Field(min_length=1)


class SampleBulkDeleteRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    ids: list[uuid.UUID] = Field(min_length=1, alias="ids")


class SampleImportResult(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    created: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
    samples: list[SampleRead] = Field(default_factory=list)
