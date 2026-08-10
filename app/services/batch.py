"""AWS Batch / Nextflow execution hooks."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import boto3
from mypy_boto3_batch import BatchClient
from mypy_boto3_batch.type_defs import ContainerOverridesTypeDef

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BatchSubmissionResult:
    job_id: str
    job_name: str
    simulated: bool
    nextflow_run_name: str
    work_dir: str


@lru_cache
def get_batch_client() -> BatchClient | None:
    if not settings.aws_batch_enabled:
        return None
    return boto3.client(
        "batch",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


class BatchService:
    def submit_nextflow_job(
        self,
        *,
        pipeline_id: str,
        pipeline_version: str,
        parameters: dict[str, Any],
        workspace: str,
        run_name: str | None = None,
    ) -> BatchSubmissionResult:
        nextflow_run_name = run_name or f"vc-{pipeline_id}-{uuid.uuid4().hex[:10]}"
        work_dir = f"{settings.nextflow_work_dir.rstrip('/')}/{workspace}/{nextflow_run_name}"
        job_name = nextflow_run_name[:128]

        container_overrides: ContainerOverridesTypeDef = {
            "command": [
                "nextflow",
                "run",
                f"nf-core/{pipeline_id}",
                "-r",
                pipeline_version,
                "-work-dir",
                work_dir,
                "-resume",
            ],
            "environment": [
                {"name": "VESSELCHAIN_WORKSPACE", "value": workspace},
                {"name": "NF_PARAMS_JSON", "value": str(parameters)},
            ],
        }

        client = get_batch_client()
        if client is None:
            simulated_id = f"sim-{uuid.uuid4().hex}"
            logger.info(
                "AWS Batch disabled; simulating submission job_id=%s pipeline=%s",
                simulated_id,
                pipeline_id,
            )
            return BatchSubmissionResult(
                job_id=simulated_id,
                job_name=job_name,
                simulated=True,
                nextflow_run_name=nextflow_run_name,
                work_dir=work_dir,
            )

        response = client.submit_job(
            jobName=job_name,
            jobQueue=settings.aws_batch_job_queue,
            jobDefinition=settings.aws_batch_job_definition,
            containerOverrides=container_overrides,
            parameters={
                "pipeline_id": pipeline_id,
                "pipeline_version": pipeline_version,
                "workspace": workspace,
            },
            tags={
                "project": "vesselchain-biologics",
                "workspace": workspace,
                "pipeline": pipeline_id,
            },
        )
        return BatchSubmissionResult(
            job_id=response["jobId"],
            job_name=job_name,
            simulated=False,
            nextflow_run_name=nextflow_run_name,
            work_dir=work_dir,
        )

    def describe_job(self, job_id: str) -> dict[str, Any]:
        client = get_batch_client()
        if client is None or job_id.startswith("sim-"):
            return {
                "jobId": job_id,
                "status": "RUNNING" if job_id.startswith("sim-") else "UNKNOWN",
                "simulated": True,
            }
        response = client.describe_jobs(jobs=[job_id])
        jobs = response.get("jobs", [])
        if not jobs:
            return {"jobId": job_id, "status": "NOT_FOUND", "simulated": False}
        job = jobs[0]
        return {
            "jobId": job.get("jobId", job_id),
            "status": job.get("status", "UNKNOWN"),
            "statusReason": job.get("statusReason"),
            "simulated": False,
        }


batch_service = BatchService()
