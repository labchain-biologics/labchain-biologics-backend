"""Pipeline run launch, listing, and SSE log streaming."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.api.deps import BioinformaticsLead, DbSession, LabOrLead, Workspace
from app.models.pipeline import JobStatus, OutputFileType, PipelineJob, RunOutputFile
from app.schemas.pipeline import PipelineJobRead, RunCreateRequest
from app.services.audit_service import audit_service
from app.services.batch import batch_service
from app.services.pipelines_catalog import get_pipeline

router = APIRouter(prefix="/runs", tags=["runs"])


def _seed_placeholder_outputs(job: PipelineJob, workspace: str) -> list[RunOutputFile]:
    """Attach representative output file metadata for downstream result endpoints."""
    return [
        RunOutputFile(
            pipeline_job_id=job.id,
            workspace=workspace,
            file_type=OutputFileType.vcf,
            filename=f"{job.nextflow_run_name or job.id}.vcf.gz",
            s3_key=f"{workspace}/results/{job.id}/variants.vcf.gz",
            size_bytes=0,
            metadata_json={"format": "vcf"},
        ),
        RunOutputFile(
            pipeline_job_id=job.id,
            workspace=workspace,
            file_type=OutputFileType.bam,
            filename=f"{job.nextflow_run_name or job.id}.bam",
            s3_key=f"{workspace}/results/{job.id}/aligned.bam",
            size_bytes=0,
            metadata_json={"format": "bam"},
        ),
        RunOutputFile(
            pipeline_job_id=job.id,
            workspace=workspace,
            file_type=OutputFileType.multiqc,
            filename="multiqc_report.html",
            s3_key=f"{workspace}/results/{job.id}/multiqc_report.html",
            size_bytes=0,
            metadata_json={"format": "html"},
        ),
    ]


@router.post("", response_model=PipelineJobRead, status_code=status.HTTP_201_CREATED)
async def launch_run(
    payload: RunCreateRequest,
    db: DbSession,
    workspace: Workspace,
    current_user: BioinformaticsLead,
) -> PipelineJob:
    catalog_item = get_pipeline(payload.pipeline_id)
    if catalog_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown pipeline '{payload.pipeline_id}'",
        )

    version = (
        payload.pipeline_version if payload.pipeline_version != "latest" else catalog_item.version
    )
    merged_params = {**catalog_item.default_params, **payload.parameters}

    submission = batch_service.submit_nextflow_job(
        pipeline_id=payload.pipeline_id,
        pipeline_version=version,
        parameters=merged_params,
        workspace=workspace,
        run_name=payload.run_name,
    )

    now = datetime.now(UTC)
    job = PipelineJob(
        workspace=workspace,
        pipeline_id=payload.pipeline_id,
        pipeline_name=catalog_item.name,
        pipeline_version=version,
        status=JobStatus.submitted if not submission.simulated else JobStatus.running,
        sequencing_run_id=payload.sequencing_run_id,
        sample_ids=[str(sample_id) for sample_id in payload.sample_ids],
        parameters=merged_params,
        aws_batch_job_id=submission.job_id,
        nextflow_run_name=submission.nextflow_run_name,
        work_dir=submission.work_dir,
        launched_by=current_user.id,
        started_at=now,
        log_buffer=(
            f"[{now.isoformat()}] Submitted Nextflow run '{submission.nextflow_run_name}' "
            f"for pipeline {catalog_item.name}@{version}\n"
            f"[{now.isoformat()}] Batch job id: {submission.job_id} "
            f"(simulated={submission.simulated})\n"
        ),
    )
    db.add(job)
    await db.flush()

    for output in _seed_placeholder_outputs(job, workspace):
        db.add(output)
    await db.flush()

    await audit_service.record(
        db,
        actor=current_user,
        action="launch",
        entity_type="pipeline_job",
        entity_id=job.id,
        workspace=workspace,
        after_state={
            "pipelineId": job.pipeline_id,
            "status": job.status.value,
            "awsBatchJobId": job.aws_batch_job_id,
            "nextflowRunName": job.nextflow_run_name,
        },
    )

    result = await db.execute(
        select(PipelineJob)
        .where(PipelineJob.id == job.id)
        .options(selectinload(PipelineJob.output_files))
    )
    return result.scalar_one()


@router.get("", response_model=list[PipelineJobRead])
async def list_runs(
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[PipelineJob]:
    stmt = (
        select(PipelineJob)
        .where(PipelineJob.workspace == workspace)
        .options(selectinload(PipelineJob.output_files))
        .order_by(PipelineJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if status_filter is not None:
        stmt = stmt.where(PipelineJob.status == status_filter)
    result = await db.execute(stmt)
    return list(result.scalars().unique().all())


@router.get("/{run_id}", response_model=PipelineJobRead)
async def get_run(
    run_id: uuid.UUID,
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
) -> PipelineJob:
    return await _get_workspace_job(db, workspace, run_id)


@router.get("/{run_id}/logs/stream")
async def stream_run_logs(
    run_id: uuid.UUID,
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
) -> EventSourceResponse:
    job = await _get_workspace_job(db, workspace, run_id)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        lines = [line for line in (job.log_buffer or "").splitlines() if line]
        cursor = 0
        for line in lines:
            cursor += 1
            yield {"event": "log", "data": line, "id": str(cursor)}

        progressive = [
            "Executor starting Nextflow processes",
            "Staging input FastQ files from S3",
            "Running alignment / quantification",
            "Writing MultiQC report",
            "Pipeline completed successfully",
        ]
        for index, message in enumerate(progressive, start=1):
            if job.status in {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}:
                break
            await asyncio.sleep(1)
            stamp = datetime.now(UTC).isoformat()
            line = f"[{stamp}] {message}"
            cursor += 1
            yield {"event": "log", "data": line, "id": str(cursor)}
            if index == len(progressive):
                yield {
                    "event": "status",
                    "data": JobStatus.succeeded.value,
                    "id": str(cursor + 1),
                }

        yield {"event": "end", "data": "stream-complete", "id": str(cursor + 2)}

    return EventSourceResponse(event_generator())


async def _get_workspace_job(db: DbSession, workspace: str, run_id: uuid.UUID) -> PipelineJob:
    result = await db.execute(
        select(PipelineJob)
        .where(PipelineJob.id == run_id, PipelineJob.workspace == workspace)
        .options(selectinload(PipelineJob.output_files))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found in workspace '{workspace}'",
        )
    return job
