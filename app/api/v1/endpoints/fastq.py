"""FastQ registration and MD5 verification endpoints."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import PurePosixPath

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DbSession, LabOrLead, Workspace
from app.models.pipeline import FastqFile, FastqVerificationStatus
from app.models.sample import SampleStatus
from app.schemas.pipeline import (
    FastqRead,
    FastqRegisterRequest,
    FastqRegisterResponse,
    FastqVerifyResponse,
)
from app.services.audit_service import audit_service
from app.services.s3 import s3_service
from app.services.sample_lifecycle import (
    get_workspace_samples,
    get_workspace_sequencing_run,
    set_status,
)
from app.services.samplesheet import storage_prefix

router = APIRouter(prefix="/fastq", tags=["fastq"])


@router.post(
    "/register",
    response_model=FastqRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_fastq(
    payload: FastqRegisterRequest,
    db: DbSession,
    workspace: Workspace,
    current_user: LabOrLead,
) -> FastqRegisterResponse:
    linked_samples = (
        await get_workspace_samples(db, workspace, [payload.sample_id])
        if payload.sample_id is not None
        else []
    )
    if payload.sequencing_run_id is not None:
        await get_workspace_sequencing_run(db, workspace, payload.sequencing_run_id)
    fastq_id = uuid.uuid4()
    prefix = storage_prefix(workspace)
    if payload.s3_key is not None and not payload.s3_key.startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"s3Key must be under '{prefix}'",
        )
    # One key per record by default, so a new upload never replaces another record's file.
    safe_name = PurePosixPath(payload.filename.replace("\\", "/")).name or "reads.fastq.gz"
    s3_key = payload.s3_key or f"{prefix}{fastq_id}/{safe_name}"
    fastq = FastqFile(
        id=fastq_id,
        workspace=workspace,
        filename=payload.filename,
        s3_key=s3_key,
        size_bytes=payload.size_bytes,
        expected_md5=payload.expected_md5.lower() if payload.expected_md5 else None,
        sample_id=payload.sample_id,
        sequencing_run_id=payload.sequencing_run_id,
        read_pair=payload.read_pair,
        verification_status=FastqVerificationStatus.pending,
    )
    db.add(fastq)
    await db.flush()

    upload_url = s3_service.generate_presigned_upload_url(s3_key, content_type="application/gzip")

    await audit_service.record(
        db,
        actor=current_user,
        action="register",
        entity_type="fastq_file",
        entity_id=fastq.id,
        workspace=workspace,
        after_state={
            "filename": fastq.filename,
            "s3Key": fastq.s3_key,
            "sizeBytes": fastq.size_bytes,
            "sampleId": str(fastq.sample_id) if fastq.sample_id else None,
            "sequencingRunId": str(fastq.sequencing_run_id) if fastq.sequencing_run_id else None,
        },
    )
    await set_status(
        db,
        linked_samples,
        SampleStatus.fastq_received,
        actor=current_user,
        reason=f"FASTQ {fastq.filename} registered",
    )

    return FastqRegisterResponse(
        id=fastq.id,
        filename=fastq.filename,
        s3_key=fastq.s3_key,
        size_bytes=fastq.size_bytes,
        expected_md5=fastq.expected_md5,
        verification_status=fastq.verification_status,
        upload_url=upload_url,
        workspace=fastq.workspace,
        created_at=fastq.created_at,
    )


@router.get("", response_model=list[FastqRead])
async def list_fastq(
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
    sample_id: uuid.UUID | None = Query(default=None, alias="sampleId"),
    sequencing_run_id: uuid.UUID | None = Query(default=None, alias="sequencingRunId"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[FastqFile]:
    stmt = select(FastqFile).where(FastqFile.workspace == workspace)
    if sample_id is not None:
        stmt = stmt.where(FastqFile.sample_id == sample_id)
    if sequencing_run_id is not None:
        stmt = stmt.where(FastqFile.sequencing_run_id == sequencing_run_id)
    stmt = stmt.order_by(FastqFile.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{fastq_id}", response_model=FastqRead)
async def get_fastq(
    fastq_id: uuid.UUID,
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
) -> FastqFile:
    return await _get_workspace_fastq(db, workspace, fastq_id)


async def _get_workspace_fastq(db: DbSession, workspace: str, fastq_id: uuid.UUID) -> FastqFile:
    result = await db.execute(
        select(FastqFile).where(FastqFile.id == fastq_id, FastqFile.workspace == workspace)
    )
    fastq = result.scalar_one_or_none()
    if fastq is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FastQ file {fastq_id} not found",
        )
    return fastq


@router.post("/{fastq_id}/verify", response_model=FastqVerifyResponse)
async def verify_fastq(
    fastq_id: uuid.UUID,
    db: DbSession,
    workspace: Workspace,
    current_user: LabOrLead,
) -> FastqVerifyResponse:
    fastq = await _get_workspace_fastq(db, workspace, fastq_id)
    if not fastq.s3_key.startswith(storage_prefix(workspace)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{fastq.filename} is stored outside this workspace and cannot be verified",
        )
    try:
        checksum = await asyncio.to_thread(s3_service.object_checksum, fastq.s3_key)
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not read {fastq.filename} from object storage: {exc}",
        ) from exc
    if checksum is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{fastq.filename} has not been uploaded yet",
        )

    computed = checksum.md5
    fastq.computed_md5 = computed
    fastq.size_bytes = checksum.size_bytes
    fastq.verified_etag = checksum.etag
    if fastq.expected_md5 is None or fastq.expected_md5.lower() == computed:
        fastq.verification_status = FastqVerificationStatus.verified
    else:
        fastq.verification_status = FastqVerificationStatus.mismatch

    await db.flush()
    await audit_service.record(
        db,
        actor=current_user,
        action="verify",
        entity_type="fastq_file",
        entity_id=fastq.id,
        workspace=workspace,
        after_state={
            "computedMd5": computed,
            "sizeBytes": fastq.size_bytes,
            "etag": checksum.etag,
            "expectedMd5": fastq.expected_md5,
            "verificationStatus": fastq.verification_status.value,
        },
    )

    return FastqVerifyResponse(
        id=fastq.id,
        expected_md5=fastq.expected_md5,
        computed_md5=computed,
        verification_status=fastq.verification_status,
    )
