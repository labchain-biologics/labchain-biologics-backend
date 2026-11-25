"""Pipeline run lifecycle after submission: Nextflow weblog events, AWS Batch status, outputs.

Two independent signals can move a run forward; both are idempotent:

- Nextflow ``-with-weblog`` events posted to ``POST /runs/{id}/events`` (fine-grained:
  per-process progress, error message);
- AWS Batch head-job status, polled by ``run_monitor`` (coarse but always available).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.pipeline import JobStatus, OutputFileType, PipelineJob, RunOutputFile
from app.models.sample import Sample, SampleStatus
from app.schemas.pipeline import WeblogEvent
from app.services.audit_service import audit_service
from app.services.batch import batch_service
from app.services.s3 import StoredObject, s3_service
from app.services.sample_lifecycle import set_status

logger = logging.getLogger(__name__)

TERMINAL = frozenset({JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled})
MAX_OUTPUT_FILES = 2000
_BATCH_ACTIVE = {"SUBMITTED", "PENDING", "RUNNABLE", "STARTING"}


def weblog_token(job_id: uuid.UUID) -> str:
    """Per-run secret Nextflow sends back with weblog events (it cannot send auth headers)."""
    message = f"weblog:{job_id}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def verify_weblog_token(job_id: uuid.UUID, token: str) -> bool:
    return hmac.compare_digest(weblog_token(job_id), token)


def weblog_url(job_id: uuid.UUID) -> str | None:
    if not settings.public_api_url:
        return None
    base = settings.public_api_url.rstrip("/")
    return f"{base}{settings.api_v1_prefix}/runs/{job_id}/events?token={weblog_token(job_id)}"


def append_log(job: PipelineJob, message: str, at: datetime | None = None) -> None:
    stamp = (at or datetime.now(UTC)).isoformat()
    job.log_buffer = f"{job.log_buffer or ''}[{stamp}] {message}\n"


def classify_output(key: str) -> OutputFileType:
    name = key.rsplit("/", 1)[-1].lower()
    if name == "multiqc_report.html":
        return OutputFileType.multiqc
    if name.endswith((".vcf", ".vcf.gz")):
        return OutputFileType.vcf
    if name.endswith((".bam", ".cram")):
        return OutputFileType.bam
    return OutputFileType.other


async def collect_outputs(db: AsyncSession, job: PipelineJob) -> int:
    """Register every object under the run's output directory. Returns the number added."""
    if not job.output_dir:
        return 0
    prefix = s3_service.key_from_uri(job.output_dir).rstrip("/") + "/"
    objects: list[StoredObject] = await asyncio.to_thread(
        s3_service.list_objects, prefix, limit=MAX_OUTPUT_FILES
    )
    existing = await db.execute(
        select(RunOutputFile.s3_key).where(RunOutputFile.pipeline_job_id == job.id)
    )
    known = set(existing.scalars().all())
    added = 0
    for obj in objects:
        if obj.key in known:
            continue
        db.add(
            RunOutputFile(
                pipeline_job_id=job.id,
                workspace=job.workspace,
                file_type=classify_output(obj.key),
                filename=obj.key.rsplit("/", 1)[-1],
                s3_key=obj.key,
                size_bytes=obj.size_bytes,
                metadata_json={"relativePath": obj.key[len(prefix) :]},
            )
        )
        added += 1
    await db.flush()
    return added


async def _job_samples(db: AsyncSession, job: PipelineJob) -> list[Sample]:
    ids = [uuid.UUID(str(sample_id)) for sample_id in job.sample_ids]
    if not ids:
        return []
    result = await db.execute(
        select(Sample).where(Sample.workspace == job.workspace, Sample.id.in_(ids))
    )
    return list(result.scalars().all())


async def mark_running(db: AsyncSession, job: PipelineJob, at: datetime | None = None) -> None:
    if job.status in TERMINAL or job.status == JobStatus.running:
        return
    before = job.status
    job.status = JobStatus.running
    job.started_at = job.started_at or at or datetime.now(UTC)
    await db.flush()
    await _audit_status(db, job, before, "execution started")


async def finalize(
    db: AsyncSession,
    job: PipelineJob,
    *,
    success: bool,
    reason: str | None = None,
    at: datetime | None = None,
) -> None:
    """Terminal transition: record outputs and move samples to ``completed`` on success."""
    if job.status in TERMINAL:
        return
    before = job.status
    job.status = JobStatus.succeeded if success else JobStatus.failed
    job.finished_at = at or datetime.now(UTC)
    append_log(
        job, f"Run {'succeeded' if success else 'failed'}" + (f": {reason}" if reason else "")
    )
    try:
        added = await collect_outputs(db, job)
        append_log(job, f"{added} output file(s) registered from {job.output_dir}")
    except Exception as exc:  # noqa: BLE001 - storage errors must not lose the status change
        logger.warning("Output collection failed for run %s: %s", job.id, exc)
        append_log(job, f"Output collection failed: {exc}")
    await db.flush()
    await _audit_status(db, job, before, reason)
    if success:
        await set_status(
            db,
            await _job_samples(db, job),
            SampleStatus.completed,
            actor=None,
            reason=f"Pipeline run {job.id} succeeded",
        )


async def _audit_status(
    db: AsyncSession, job: PipelineJob, before: JobStatus, reason: str | None
) -> None:
    await audit_service.record(
        db,
        actor=None,
        action="status_change",
        entity_type="pipeline_job",
        entity_id=job.id,
        workspace=job.workspace,
        before_state={"status": before.value},
        after_state={"status": job.status.value},
        reason=reason,
    )


def _event_time(event: WeblogEvent) -> datetime:
    return event.utc_time or datetime.now(UTC)


async def apply_weblog_event(db: AsyncSession, job: PipelineJob, event: WeblogEvent) -> None:
    at = _event_time(event)
    progress: dict[str, Any] = dict(job.progress or {})
    progress["lastEvent"] = event.event
    progress["lastEventAt"] = at.isoformat()

    if event.event == "started":
        append_log(job, f"Nextflow run '{event.run_name}' started", at)
        await mark_running(db, job, at)
    elif event.event.startswith("process_"):
        trace = event.trace or {}
        name = str(trace.get("name") or trace.get("process") or "unknown process")
        trace_status = str(trace.get("status") or event.event.removeprefix("process_").upper())
        if event.event == "process_submitted":
            progress["processesSubmitted"] = int(progress.get("processesSubmitted", 0)) + 1
        elif event.event == "process_started":
            progress["currentProcess"] = name
        elif event.event == "process_completed":
            key = "processesFailed" if trace_status == "FAILED" else "processesCompleted"
            progress[key] = int(progress.get(key, 0)) + 1
        append_log(job, f"[{trace_status}] {name}", at)
        await mark_running(db, job, at)
    elif event.event == "error":
        workflow = (event.metadata or {}).get("workflow", {})
        message = workflow.get("errorMessage") or "Nextflow reported an error"
        progress["errorMessage"] = str(message)
        append_log(job, f"ERROR: {message}", at)
    elif event.event == "completed":
        workflow = (event.metadata or {}).get("workflow", {})
        success = bool(workflow.get("success"))
        reason = None if success else str(workflow.get("errorMessage") or "pipeline failed")
        job.progress = progress
        await finalize(db, job, success=success, reason=reason, at=at)
        return
    else:
        append_log(job, f"Nextflow event '{event.event}'", at)
    job.progress = progress
    await db.flush()


async def reconcile_batch_job(db: AsyncSession, job: PipelineJob) -> None:
    """Align a submitted run with its AWS Batch head job."""
    if job.status in TERMINAL or not job.aws_batch_job_id:
        return
    info = await asyncio.to_thread(batch_service.describe_job, job.aws_batch_job_id)
    batch_status = str(info.get("status"))
    if batch_status == "RUNNING":
        await mark_running(db, job)
    elif batch_status == "SUCCEEDED":
        await finalize(db, job, success=True, reason="AWS Batch job succeeded")
    elif batch_status in {"FAILED", "NOT_FOUND"}:
        reason = str(info.get("statusReason") or f"AWS Batch job {batch_status.lower()}")
        await finalize(db, job, success=False, reason=reason)
    elif batch_status not in _BATCH_ACTIVE:
        logger.warning("Unexpected AWS Batch status %s for run %s", batch_status, job.id)


async def reconcile_all(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """One monitor pass over every submitted/running run. Returns the number checked."""
    async with session_factory() as db:
        result = await db.execute(
            select(PipelineJob.id).where(
                PipelineJob.status.in_([JobStatus.submitted, JobStatus.running]),
                PipelineJob.aws_batch_job_id.is_not(None),
            )
        )
        job_ids = list(result.scalars().all())
    for job_id in job_ids:
        async with session_factory() as db:
            job = await db.get(PipelineJob, job_id, with_for_update=True)
            if job is None:
                continue
            try:
                await reconcile_batch_job(db, job)
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("Reconciling run %s failed", job_id)
    return len(job_ids)


async def run_monitor(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Background loop started with the app when AWS Batch is enabled."""
    while True:
        try:
            await reconcile_all(session_factory)
        except Exception:
            logger.exception("Run monitor pass failed")
        await asyncio.sleep(settings.run_monitor_interval_seconds)
