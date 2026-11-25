"""Unit tests for sample LIMS Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.sample import OmicsModality, QcStatus
from app.schemas.sample import (
    SampleBulkDeleteRequest,
    SampleBulkPatchRequest,
    SampleCreate,
    SampleRead,
    SampleUpdate,
)


def test_sample_create_accepts_camel_case_aliases(
    sample_create_payload: dict[str, object],
) -> None:
    sample = SampleCreate.model_validate(sample_create_payload)
    assert sample.sample_code == "S-001"
    assert sample.modality == OmicsModality.transcriptomics
    assert sample.rin_din == 8.5
    assert sample.concentration_ng_ul == 120.0
    assert sample.qc_status == QcStatus.pending


def test_sample_create_serializes_to_camel_case() -> None:
    sample = SampleCreate(
        sample_code="S-002",
        modality=OmicsModality.genomics,
        rin_din=9.0,
        concentration_ng_ul=50.0,
    )
    dumped = sample.model_dump(by_alias=True)
    assert dumped["sampleCode"] == "S-002"
    assert dumped["rinDin"] == 9.0
    assert dumped["concentrationNgUl"] == 50.0
    assert dumped["qcStatus"] == "pending"


def test_sample_create_normalizes_pass_underscore_qc_status() -> None:
    sample = SampleCreate(
        sample_code="S-003",
        modality=OmicsModality.genomics,
        qc_status="pass_",  # type: ignore[arg-type]
    )
    assert sample.qc_status == QcStatus.pass_


def test_sample_create_rejects_invalid_rin_din() -> None:
    with pytest.raises(ValidationError):
        SampleCreate(
            sample_code="S-004",
            modality=OmicsModality.transcriptomics,
            rin_din=11.0,
        )


def test_sample_create_rejects_negative_concentration() -> None:
    with pytest.raises(ValidationError):
        SampleCreate(
            sample_code="S-005",
            modality=OmicsModality.transcriptomics,
            concentration_ng_ul=-1.0,
        )


def test_sample_update_partial_fields() -> None:
    update = SampleUpdate.model_validate({"qcStatus": "fail", "qcNotes": "low RIN"})
    assert update.qc_status == QcStatus.fail
    assert update.qc_notes == "low RIN"
    assert update.sample_code is None


def test_sample_read_from_attributes() -> None:
    now = datetime.now(UTC)
    sample_id = uuid.uuid4()
    read = SampleRead.model_validate(
        {
            "id": sample_id,
            "workspace": "default",
            "sample_code": "S-100",
            "modality": OmicsModality.epigenomics,
            "qc_status": QcStatus.warn,
            "status": "fastq_received",
            "a260_280": 1.9,
            "created_at": now,
            "updated_at": now,
            "metadata_json": {},
        }
    )
    assert read.id == sample_id
    dumped = read.model_dump(by_alias=True)
    assert dumped["createdAt"] == now
    assert dumped["sampleCode"] == "S-100"
    assert dumped["status"] == "fastq_received"
    assert dumped["a260280"] == 1.9


def test_sample_create_ignores_server_managed_status() -> None:
    created = SampleCreate.model_validate(
        {"sampleCode": "S-200", "modality": "genomics", "status": "completed", "assay": "exome"}
    )
    assert "status" not in created.model_dump()
    assert created.assay == "exome"


def test_sample_create_rejects_unknown_assay() -> None:
    with pytest.raises(ValidationError):
        SampleCreate.model_validate({"sampleCode": "S-201", "modality": "genomics", "assay": "WGS"})


def test_bulk_patch_requires_at_least_one_item() -> None:
    with pytest.raises(ValidationError):
        SampleBulkPatchRequest(items=[])


def test_bulk_delete_requires_at_least_one_id() -> None:
    with pytest.raises(ValidationError):
        SampleBulkDeleteRequest(ids=[])


def test_bulk_delete_accepts_ids() -> None:
    sample_id = uuid.uuid4()
    req = SampleBulkDeleteRequest(ids=[sample_id])
    assert req.ids == [sample_id]
