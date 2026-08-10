"""Sample LIMS CRUD, CSV import, and bulk operations."""

from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select

from app.api.deps import DbSession, LabOrLead, Workspace
from app.models.sample import OmicsModality, QcStatus, Sample
from app.schemas.sample import (
    SampleBulkDeleteRequest,
    SampleBulkPatchRequest,
    SampleCreate,
    SampleImportResult,
    SampleRead,
    SampleUpdate,
)
from app.services.audit_service import audit_service

router = APIRouter(prefix="/samples", tags=["samples"])


def _sample_to_dict(sample: Sample) -> dict[str, Any]:
    return {
        "id": str(sample.id),
        "sampleCode": sample.sample_code,
        "workspace": sample.workspace,
        "modality": sample.modality.value,
        "rinDin": sample.rin_din,
        "concentrationNgUl": sample.concentration_ng_ul,
        "qcStatus": sample.qc_status.value,
        "patientId": sample.patient_id,
        "projectCode": sample.project_code,
    }


def _apply_update(sample: Sample, patch: SampleUpdate) -> None:
    data = patch.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(sample, key, value)


async def _get_workspace_sample(db: DbSession, workspace: str, sample_id: uuid.UUID) -> Sample:
    result = await db.execute(
        select(Sample).where(Sample.id == sample_id, Sample.workspace == workspace)
    )
    sample = result.scalar_one_or_none()
    if sample is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sample {sample_id} not found in workspace '{workspace}'",
        )
    return sample


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)  # type: ignore[arg-type]


@router.get("", response_model=list[SampleRead])
async def list_samples(
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
    modality: OmicsModality | None = None,
    qc_status: QcStatus | None = Query(default=None, alias="qcStatus"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Sample]:
    stmt = select(Sample).where(Sample.workspace == workspace)
    if modality is not None:
        stmt = stmt.where(Sample.modality == modality)
    if qc_status is not None:
        stmt = stmt.where(Sample.qc_status == qc_status)
    stmt = stmt.order_by(Sample.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=SampleRead, status_code=status.HTTP_201_CREATED)
async def create_sample(
    payload: SampleCreate,
    db: DbSession,
    workspace: Workspace,
    current_user: LabOrLead,
) -> Sample:
    sample = Sample(
        workspace=workspace,
        **payload.model_dump(),
    )
    db.add(sample)
    await db.flush()
    await audit_service.record(
        db,
        actor=current_user,
        action="create",
        entity_type="sample",
        entity_id=sample.id,
        workspace=workspace,
        after_state=_sample_to_dict(sample),
    )
    return sample


@router.post("/import", response_model=SampleImportResult)
async def import_samples_csv(
    db: DbSession,
    workspace: Workspace,
    current_user: LabOrLead,
    file: UploadFile = File(...),
) -> SampleImportResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are supported",
        )
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must be UTF-8 encoded",
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV is empty or missing a header row",
        )

    created_samples: list[Sample] = []
    errors: list[str] = []
    skipped = 0

    for row_number, row in enumerate(reader, start=2):
        normalized = {
            key.strip(): (value.strip() if isinstance(value, str) else value)
            for key, value in row.items()
            if key
        }
        try:
            create_payload = SampleCreate.model_validate(
                {
                    "sampleCode": normalized.get("sampleCode") or normalized.get("sample_code"),
                    "patientId": normalized.get("patientId")
                    or normalized.get("patient_id")
                    or None,
                    "projectCode": normalized.get("projectCode")
                    or normalized.get("project_code")
                    or None,
                    "modality": normalized.get("modality"),
                    "tissueType": normalized.get("tissueType")
                    or normalized.get("tissue_type")
                    or None,
                    "collectionDate": normalized.get("collectionDate")
                    or normalized.get("collection_date")
                    or None,
                    "rinDin": _optional_float(
                        normalized.get("rinDin") or normalized.get("rin_din")
                    ),
                    "concentrationNgUl": _optional_float(
                        normalized.get("concentrationNgUl") or normalized.get("concentration_ng_ul")
                    ),
                    "volumeUl": _optional_float(
                        normalized.get("volumeUl") or normalized.get("volume_ul")
                    ),
                    "qcStatus": normalized.get("qcStatus")
                    or normalized.get("qc_status")
                    or "pending",
                    "qcNotes": normalized.get("qcNotes") or normalized.get("qc_notes") or None,
                    "metadata": {},
                }
            )
        except Exception as exc:
            errors.append(f"row {row_number}: {exc}")
            skipped += 1
            continue

        sample = Sample(workspace=workspace, **create_payload.model_dump())
        db.add(sample)
        created_samples.append(sample)

    await db.flush()
    for sample in created_samples:
        await audit_service.record(
            db,
            actor=current_user,
            action="import",
            entity_type="sample",
            entity_id=sample.id,
            workspace=workspace,
            after_state=_sample_to_dict(sample),
        )

    return SampleImportResult(
        created=len(created_samples),
        skipped=skipped,
        errors=errors,
        samples=created_samples,
    )


@router.patch("/bulk", response_model=list[SampleRead])
async def bulk_patch_samples(
    payload: SampleBulkPatchRequest,
    db: DbSession,
    workspace: Workspace,
    current_user: LabOrLead,
) -> list[Sample]:
    updated: list[Sample] = []
    for item in payload.items:
        sample = await _get_workspace_sample(db, workspace, item.id)
        before = _sample_to_dict(sample)
        _apply_update(sample, item.patch)
        await db.flush()
        await audit_service.record(
            db,
            actor=current_user,
            action="bulk_update",
            entity_type="sample",
            entity_id=sample.id,
            workspace=workspace,
            before_state=before,
            after_state=_sample_to_dict(sample),
        )
        updated.append(sample)
    return updated


@router.delete("/bulk", response_model=dict[str, int])
async def bulk_delete_samples(
    payload: SampleBulkDeleteRequest,
    db: DbSession,
    workspace: Workspace,
    current_user: LabOrLead,
) -> dict[str, int]:
    deleted = 0
    for sample_id in payload.ids:
        result = await db.execute(
            select(Sample).where(Sample.id == sample_id, Sample.workspace == workspace)
        )
        sample = result.scalar_one_or_none()
        if sample is None:
            continue
        before = _sample_to_dict(sample)
        await db.delete(sample)
        await audit_service.record(
            db,
            actor=current_user,
            action="bulk_delete",
            entity_type="sample",
            entity_id=sample_id,
            workspace=workspace,
            before_state=before,
        )
        deleted += 1
    return {"deleted": deleted}


@router.get("/{sample_id}", response_model=SampleRead)
async def get_sample(
    sample_id: uuid.UUID,
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
) -> Sample:
    return await _get_workspace_sample(db, workspace, sample_id)


@router.patch("/{sample_id}", response_model=SampleRead)
async def update_sample(
    sample_id: uuid.UUID,
    payload: SampleUpdate,
    db: DbSession,
    workspace: Workspace,
    current_user: LabOrLead,
) -> Sample:
    sample = await _get_workspace_sample(db, workspace, sample_id)
    before = _sample_to_dict(sample)
    _apply_update(sample, payload)
    await db.flush()
    await audit_service.record(
        db,
        actor=current_user,
        action="update",
        entity_type="sample",
        entity_id=sample.id,
        workspace=workspace,
        before_state=before,
        after_state=_sample_to_dict(sample),
    )
    return sample


@router.delete("/{sample_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sample(
    sample_id: uuid.UUID,
    db: DbSession,
    workspace: Workspace,
    current_user: LabOrLead,
) -> None:
    sample = await _get_workspace_sample(db, workspace, sample_id)
    before = _sample_to_dict(sample)
    await db.delete(sample)
    await audit_service.record(
        db,
        actor=current_user,
        action="delete",
        entity_type="sample",
        entity_id=sample_id,
        workspace=workspace,
        before_state=before,
    )
