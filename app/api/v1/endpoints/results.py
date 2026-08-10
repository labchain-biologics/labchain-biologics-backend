"""Run output parsing and presigned download URLs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, LabOrLead, Workspace
from app.core.config import settings
from app.models.pipeline import OutputFileType, PipelineJob, RunOutputFile
from app.schemas.pipeline import ResultDownloadResponse, RunOutputFileRead
from app.services.s3 import s3_service

router = APIRouter(prefix="/results", tags=["results"])


def _to_read(item: RunOutputFile) -> RunOutputFileRead:
    download_url = s3_service.generate_presigned_download_url(item.s3_key, filename=item.filename)
    return RunOutputFileRead(
        id=item.id,
        file_type=item.file_type,
        filename=item.filename,
        s3_key=item.s3_key,
        size_bytes=item.size_bytes,
        md5=item.md5,
        sample_id=item.sample_id,
        metadata_json=item.metadata_json or {},
        download_url=download_url,
        created_at=item.created_at,
    )


@router.get("", response_model=list[RunOutputFileRead])
async def list_results(
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
    run_id: uuid.UUID | None = Query(default=None, alias="runId"),
    file_type: OutputFileType | None = Query(default=None, alias="fileType"),
) -> list[RunOutputFileRead]:
    stmt = select(RunOutputFile).where(RunOutputFile.workspace == workspace)
    if run_id is not None:
        stmt = stmt.where(RunOutputFile.pipeline_job_id == run_id)
    if file_type is not None:
        stmt = stmt.where(RunOutputFile.file_type == file_type)
    stmt = stmt.order_by(RunOutputFile.created_at.desc())
    result = await db.execute(stmt)
    return [_to_read(item) for item in result.scalars().all()]


@router.get("/runs/{run_id}", response_model=list[RunOutputFileRead])
async def list_results_for_run(
    run_id: uuid.UUID,
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
) -> list[RunOutputFileRead]:
    job_result = await db.execute(
        select(PipelineJob)
        .where(PipelineJob.id == run_id, PipelineJob.workspace == workspace)
        .options(selectinload(PipelineJob.output_files))
    )
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found",
        )
    return [_to_read(item) for item in job.output_files]


@router.get("/{output_id}/download", response_model=ResultDownloadResponse)
async def get_presigned_download(
    output_id: uuid.UUID,
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
) -> ResultDownloadResponse:
    result = await db.execute(
        select(RunOutputFile).where(
            RunOutputFile.id == output_id, RunOutputFile.workspace == workspace
        )
    )
    output = result.scalar_one_or_none()
    if output is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Result file {output_id} not found",
        )

    download_url = s3_service.generate_presigned_download_url(
        output.s3_key, filename=output.filename
    )
    return ResultDownloadResponse(
        id=output.id,
        file_type=output.file_type,
        filename=output.filename,
        download_url=download_url,
        expires_in=settings.s3_presign_expire_seconds,
        md5=output.md5,
    )
