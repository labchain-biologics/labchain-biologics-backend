"""Pipeline run launch, listing, logs, SSE streaming and Nextflow weblog callbacks."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.api.deps import BioinformaticsLead, DbSession, LabOrLead, Workspace
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.pipeline import JobStatus, PipelineJob
from app.models.sample import SampleStatus
from app.schemas.pipeline import PipelineJobRead, RunCreateRequest, RunLogLine, WeblogEvent
from app.services import run_lifecycle, samplesheet
from app.services.audit_service import audit_service
from app.services.batch import (
    InvalidParameterError,
    NextflowLaunch,
    batch_service,
    build_nextflow_command,
    validate_parameters,
)
from app.services.pipelines_catalog import get_pipeline
from app.services.s3 import s3_service
from app.services.sample_lifecycle import (
    get_workspace_samples,
    get_workspace_sequencing_run,
    set_status,
)

router = APIRouter(prefix="/runs", tags=["runs"])

SSE_POLL_SECONDS = 2.0
SSE_MAX_SECONDS = 3600.0


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def _redact(command: list[str]) -> str:
    """Command line for the run log, without the weblog secret."""
    return " ".join(
        arg.split("?token=")[0] + "?token=***" if "?token=" in arg else arg for arg in command
    )


@router.post("", response_model=PipelineJobRead, status_code=status.HTTP_201_CREATED)
async def launch_run(
    payload: RunCreateRequest,
    db: DbSession,
    workspace: Workspace,
    current_user: BioinformaticsLead,
) -> PipelineJob:
    """
    Build the samplesheet from the selected samples' verified FASTQ files, store it in S3 and
    submit the Nextflow head job to AWS Batch. With AWS Batch disabled the run is recorded
    as ``pending`` and not executed.
    """
    catalog_item = get_pipeline(payload.pipeline_id)
    if catalog_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown pipeline '{payload.pipeline_id}'",
        )
    version = (
        payload.pipeline_version if payload.pipeline_version != "latest" else catalog_item.version
    )
    if version not in catalog_item.versions:
        raise _unprocessable(
            f"Version '{version}' is not available for {catalog_item.name}. "
            f"Allowed: {catalog_item.versions}"
        )
    if not samplesheet.supports(payload.pipeline_id):
        raise _unprocessable(
            f"{catalog_item.name} cannot be launched from the LIMS yet: its samplesheet needs "
            "metadata that is not recorded"
        )
    merged_params = {**catalog_item.default_params, **payload.parameters}
    try:
        validate_parameters(merged_params)
    except InvalidParameterError as exc:
        raise _unprocessable(str(exc)) from exc

    samples = await get_workspace_samples(db, workspace, payload.sample_ids)
    if payload.sequencing_run_id is not None:
        await get_workspace_sequencing_run(db, workspace, payload.sequencing_run_id)
    entries = await samplesheet.collect_entries(db, samples, s3_service.uri)
    sheet = samplesheet.build_samplesheet(payload.pipeline_id, entries)

    job_id = uuid.uuid4()
    run_name = f"lc-{payload.pipeline_id}-{job_id.hex[:12]}"
    try:
        samplesheet_uri = await asyncio.to_thread(
            s3_service.put_text,
            f"{workspace}/runs/{job_id}/samplesheet.csv",
            sheet,
            content_type="text/csv",
        )
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not store the samplesheet in object storage: {exc}",
        ) from exc

    launch = NextflowLaunch(
        pipeline_id=payload.pipeline_id,
        pipeline_version=version,
        run_name=run_name,
        work_dir=f"{settings.nextflow_work_dir.rstrip('/')}/{workspace}/{job_id}",
        input_uri=samplesheet_uri,
        outdir_uri=s3_service.uri(f"{workspace}/results/{job_id}"),
        parameters=merged_params,
        weblog_url=run_lifecycle.weblog_url(job_id),
    )
    command = build_nextflow_command(launch)
    try:
        submission = await asyncio.to_thread(batch_service.submit, launch, workspace=workspace)
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AWS Batch submission failed: {exc}",
        ) from exc

    job = PipelineJob(
        id=job_id,
        workspace=workspace,
        pipeline_id=payload.pipeline_id,
        pipeline_name=catalog_item.name,
        pipeline_version=version,
        status=JobStatus.submitted if submission.submitted else JobStatus.pending,
        sequencing_run_id=payload.sequencing_run_id,
        sample_ids=[str(sample.id) for sample in samples],
        parameters=merged_params,
        aws_batch_job_id=submission.job_id,
        nextflow_run_name=run_name,
        work_dir=launch.work_dir,
        output_dir=launch.outdir_uri,
        samplesheet_uri=samplesheet_uri,
        launched_by=current_user.id,
        progress={},
        log_buffer="",
    )
    run_lifecycle.append_log(
        job, f"Samplesheet with {len(entries)} sample(s) written to {samplesheet_uri}"
    )
    run_lifecycle.append_log(job, f"Command: {_redact(command)}")
    if submission.submitted:
        run_lifecycle.append_log(job, f"Submitted to AWS Batch as job {submission.job_id}")
    else:
        run_lifecycle.append_log(
            job,
            "Not submitted: pipeline execution is disabled on this instance "
            "(AWS_BATCH_ENABLED=false)",
        )
    db.add(job)
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
            "pipelineVersion": job.pipeline_version,
            "status": job.status.value,
            "awsBatchJobId": job.aws_batch_job_id,
            "nextflowRunName": job.nextflow_run_name,
            "sampleIds": job.sample_ids,
            "samplesheetUri": samplesheet_uri,
        },
    )
    if submission.submitted:
        await set_status(
            db,
            samples,
            SampleStatus.processing,
            actor=current_user,
            reason=f"Pipeline run {job.id} ({catalog_item.name}@{version}) submitted",
            allow_backward_to_processing=True,
        )
    return await _get_workspace_job(db, workspace, job.id)


@router.get("", response_model=list[PipelineJobRead])
async def list_runs(
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    sample_id: uuid.UUID | None = Query(default=None, alias="sampleId"),
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
    if sample_id is not None:
        stmt = stmt.where(PipelineJob.sample_ids.contains([str(sample_id)]))
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


def _parse_log_line(index: int, line: str) -> RunLogLine:
    """Split ``[ISO-8601] message`` lines as written to ``log_buffer``."""
    if line.startswith("[") and "] " in line:
        stamp, message = line[1:].split("] ", 1)
        try:
            return RunLogLine(index=index, timestamp=datetime.fromisoformat(stamp), message=message)
        except ValueError:
            pass
    return RunLogLine(index=index, timestamp=None, message=line)


def _log_lines(job: PipelineJob) -> list[str]:
    return [line for line in (job.log_buffer or "").splitlines() if line]


@router.get("/{run_id}/logs", response_model=list[RunLogLine])
async def get_run_logs(
    run_id: uuid.UUID,
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
    after: int = Query(default=-1, ge=-1, description="Only lines with index > after"),
) -> list[RunLogLine]:
    """Run log as JSON lines, for clients that poll instead of using the SSE stream."""
    job = await _get_workspace_job(db, workspace, run_id)
    return [_parse_log_line(i, line) for i, line in enumerate(_log_lines(job)) if i > after]


@router.get("/{run_id}/logs/stream")
async def stream_run_logs(
    run_id: uuid.UUID,
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
) -> EventSourceResponse:
    """
    Server-sent events: ``log`` for each run log line as it is written, ``status`` when the
    run status changes, ``end`` once the run is finished, was never submitted, or after an
    hour.
    """
    await _get_workspace_job(db, workspace, run_id)
    return EventSourceResponse(_log_events(workspace, run_id))


async def _log_events(workspace: str, run_id: uuid.UUID) -> AsyncIterator[dict[str, str]]:
    sent = 0
    last_status: JobStatus | None = None
    waited = 0.0
    while True:
        # A fresh session per poll: the request-scoped session is closed while streaming.
        async with AsyncSessionLocal() as session:
            job = await session.scalar(
                select(PipelineJob).where(
                    PipelineJob.id == run_id, PipelineJob.workspace == workspace
                )
            )
        if job is None:
            yield {"event": "end", "data": "run-not-found"}
            return
        lines = _log_lines(job)
        for index in range(sent, len(lines)):
            yield {"event": "log", "data": lines[index], "id": str(index)}
        sent = len(lines)
        if job.status != last_status:
            last_status = job.status
            yield {"event": "status", "data": job.status.value}
        never_submitted = job.status == JobStatus.pending and job.aws_batch_job_id is None
        if job.status in run_lifecycle.TERMINAL or never_submitted or waited >= SSE_MAX_SECONDS:
            yield {"event": "end", "data": job.status.value}
            return
        await asyncio.sleep(SSE_POLL_SECONDS)
        waited += SSE_POLL_SECONDS


@router.post(
    "/{run_id}/events",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Nextflow weblog callback",
)
async def receive_weblog_event(
    run_id: uuid.UUID,
    event: WeblogEvent,
    db: DbSession,
    token: str = Query(min_length=16, max_length=128),
) -> None:
    """
    Endpoint passed to Nextflow as ``-with-weblog``. Authenticated by the per-run token in
    the URL (Nextflow cannot send headers); not workspace-scoped and not for API clients.
    """
    if not run_lifecycle.verify_weblog_token(run_id, token):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    job = await db.get(PipelineJob, run_id, with_for_update=True)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    await run_lifecycle.apply_weblog_event(db, job, event)


async def _get_workspace_job(db: DbSession, workspace: str, run_id: uuid.UUID) -> PipelineJob:
    result = await db.execute(
        select(PipelineJob)
        .where(PipelineJob.id == run_id, PipelineJob.workspace == workspace)
        .options(selectinload(PipelineJob.output_files))
        .execution_options(populate_existing=True)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found in workspace '{workspace}'",
        )
    return job
