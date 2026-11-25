"""Sample LIMS CRUD, CSV import, and bulk operations."""

from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select

from app.api.deps import DbSession, LabOrLead, Workspace
from app.models.sample import OmicsModality, QcStatus, Sample, SampleAssay, SampleStatus
from app.models.user import User
from app.schemas.sample import (
    SampleBulkDeleteRequest,
    SampleBulkPatchRequest,
    SampleCreate,
    SampleImportResult,
    SampleRead,
    SampleUpdate,
)
from app.services.audit_service import audit_service
from app.services.sample_lifecycle import soft_delete

router = APIRouter(prefix="/samples", tags=["samples"])


def _sample_to_dict(sample: Sample) -> dict[str, Any]:
    """Full JSON snapshot of a sample for the audit trail (camelCase, like the API)."""
    return SampleRead.model_validate(sample).model_dump(mode="json", by_alias=True)


def _apply_update(sample: Sample, patch: SampleUpdate) -> None:
    data = patch.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(sample, key, value)


async def _get_workspace_sample(db: DbSession, workspace: str, sample_id: uuid.UUID) -> Sample:
    result = await db.execute(
        select(Sample).where(
            Sample.id == sample_id, Sample.workspace == workspace, Sample.is_active()
        )
    )
    sample = result.scalar_one_or_none()
    if sample is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sample {sample_id} not found in workspace '{workspace}'",
        )
    return sample


async def _existing_codes(db: DbSession, workspace: str, codes: set[str]) -> set[str]:
    """Codes already used in the workspace, including by deleted samples (never reused)."""
    if not codes:
        return set()
    result = await db.execute(
        select(Sample.sample_code).where(
            Sample.workspace == workspace, Sample.sample_code.in_(codes)
        )
    )
    return set(result.scalars().all())


async def _ensure_code_available(
    db: DbSession, workspace: str, code: str, *, exclude_id: uuid.UUID | None = None
) -> None:
    stmt = select(Sample.deleted_at).where(
        Sample.workspace == workspace, Sample.sample_code == code
    )
    if exclude_id is not None:
        stmt = stmt.where(Sample.id != exclude_id)
    existing = (await db.execute(stmt)).first()
    if existing is not None:
        reason = (
            "was used by a deleted sample; sample codes are not reused"
            if existing.deleted_at is not None
            else "already exists"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sample code '{code}' {reason} in workspace '{workspace}'",
        )


async def _update_with_audit(
    db: DbSession,
    workspace: str,
    sample: Sample,
    patch: SampleUpdate,
    *,
    action: str,
    actor: User,
) -> Sample:
    if patch.sample_code is not None and patch.sample_code != sample.sample_code:
        await _ensure_code_available(db, workspace, patch.sample_code, exclude_id=sample.id)
    before = _sample_to_dict(sample)
    _apply_update(sample, patch)
    await db.flush()
    await audit_service.record(
        db,
        actor=actor,
        action=action,
        entity_type="sample",
        entity_id=sample.id,
        workspace=workspace,
        before_state=before,
        after_state=_sample_to_dict(sample),
    )
    return sample


def _csv_row_payload(row: dict[str, str | None]) -> dict[str, Any]:
    """Map a CSV row to ``SampleCreate`` input. Columns may use camelCase or snake_case."""
    payload: dict[str, Any] = {}
    for name, field in SampleCreate.model_fields.items():
        if name == "metadata_json":
            continue
        alias = field.alias or name
        value = row.get(alias) or row.get(name)
        if value not in (None, ""):
            payload[alias] = value
    payload.setdefault("qcStatus", QcStatus.pending.value)
    return payload


@router.get("", response_model=list[SampleRead])
async def list_samples(
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
    modality: OmicsModality | None = None,
    assay: SampleAssay | None = None,
    sample_status: SampleStatus | None = Query(default=None, alias="status"),
    qc_status: QcStatus | None = Query(default=None, alias="qcStatus"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Sample]:
    stmt = select(Sample).where(Sample.workspace == workspace, Sample.is_active())
    if modality is not None:
        stmt = stmt.where(Sample.modality == modality)
    if assay is not None:
        stmt = stmt.where(Sample.assay == assay)
    if sample_status is not None:
        stmt = stmt.where(Sample.status == sample_status)
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
    await _ensure_code_available(db, workspace, payload.sample_code)
    sample = Sample(
        workspace=workspace,
        status=SampleStatus.registered,
        created_by=current_user.id,
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
    """
    Import samples from a UTF-8 CSV. Columns are the ``SampleCreate`` fields, in camelCase
    (``sampleCode``) or snake_case (``sample_code``). Rows with a sample code that already
    exists in the workspace, or appears twice in the file, are skipped and reported.
    """
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

    parsed: list[tuple[int, SampleCreate]] = []
    errors: list[str] = []
    skipped = 0
    for row_number, row in enumerate(reader, start=2):
        normalized = {
            key.strip(): (value.strip() if isinstance(value, str) else value)
            for key, value in row.items()
            if key
        }
        try:
            parsed.append((row_number, SampleCreate.model_validate(_csv_row_payload(normalized))))
        except (ValidationError, ValueError, TypeError) as exc:
            errors.append(f"row {row_number}: {exc}")
            skipped += 1

    taken = await _existing_codes(db, workspace, {item.sample_code for _, item in parsed})
    created_samples: list[Sample] = []
    for row_number, item in parsed:
        if item.sample_code in taken:
            errors.append(f"row {row_number}: sample code '{item.sample_code}' already exists")
            skipped += 1
            continue
        taken.add(item.sample_code)
        sample = Sample(
            workspace=workspace,
            status=SampleStatus.registered,
            created_by=current_user.id,
            **item.model_dump(),
        )
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
        samples=[SampleRead.model_validate(sample) for sample in created_samples],
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
        updated.append(
            await _update_with_audit(
                db, workspace, sample, item.patch, action="bulk_update", actor=current_user
            )
        )
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
            select(Sample).where(
                Sample.id == sample_id, Sample.workspace == workspace, Sample.is_active()
            )
        )
        sample = result.scalar_one_or_none()
        if sample is None:
            continue
        await soft_delete(
            db,
            sample,
            actor=current_user,
            action="bulk_delete",
            before_state=_sample_to_dict(sample),
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
    return await _update_with_audit(
        db, workspace, sample, payload, action="update", actor=current_user
    )


@router.delete("/{sample_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sample(
    sample_id: uuid.UUID,
    db: DbSession,
    workspace: Workspace,
    current_user: LabOrLead,
) -> None:
    sample = await _get_workspace_sample(db, workspace, sample_id)
    await soft_delete(
        db, sample, actor=current_user, action="delete", before_state=_sample_to_dict(sample)
    )
