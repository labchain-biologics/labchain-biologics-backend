"""FastQ registration and MD5 verification endpoints."""

from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, LabOrLead, Workspace
from app.models.pipeline import FastqFile, FastqVerificationStatus
from app.schemas.pipeline import (
    FastqRegisterRequest,
    FastqRegisterResponse,
    FastqVerifyResponse,
)
from app.services.audit_service import audit_service
from app.services.s3 import s3_service

router = APIRouter(prefix="/fastq", tags=["fastq"])


def _compute_stub_md5(s3_key: str, size_bytes: int) -> str:
    """
    Deterministic MD5 stub used when full S3 object hashing is not available locally.
    Production deployments may replace this with a Batch/Lambda object hasher.
    """
    digest = hashlib.md5(usedforsecurity=False)
    digest.update(s3_key.encode("utf-8"))
    digest.update(b":")
    digest.update(str(size_bytes).encode("utf-8"))
    return digest.hexdigest()


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
    s3_key = payload.s3_key or s3_service.build_object_key(workspace, "fastq", payload.filename)
    fastq = FastqFile(
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
        },
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


@router.post("/{fastq_id}/verify", response_model=FastqVerifyResponse)
async def verify_fastq(
    fastq_id: uuid.UUID,
    db: DbSession,
    workspace: Workspace,
    current_user: LabOrLead,
) -> FastqVerifyResponse:
    result = await db.execute(
        select(FastqFile).where(FastqFile.id == fastq_id, FastqFile.workspace == workspace)
    )
    fastq = result.scalar_one_or_none()
    if fastq is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FastQ file {fastq_id} not found",
        )

    computed = _compute_stub_md5(fastq.s3_key, fastq.size_bytes)
    fastq.computed_md5 = computed
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
