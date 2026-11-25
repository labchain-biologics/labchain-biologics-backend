"""Nextflow command construction and AWS Batch submission / status."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import boto3
from mypy_boto3_batch import BatchClient
from mypy_boto3_batch.type_defs import ContainerOverridesTypeDef

from app.core.config import settings

logger = logging.getLogger(__name__)

# Nextflow run names: lowercase letter first, then letters, digits, single - or _ separators.
_RUN_NAME = re.compile(r"^[a-z](?:[a-z\d]|[-_](?=[a-z\d])){0,79}$")
# nf-core parameter names (`--genome`, `--skip_qc`, `--FW_primer`).
_PARAM_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
# Parameters set by the platform; users cannot override them.
RESERVED_PARAMS = frozenset({"input", "outdir"})


class InvalidParameterError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NextflowLaunch:
    pipeline_id: str
    pipeline_version: str
    run_name: str
    work_dir: str
    input_uri: str
    outdir_uri: str
    parameters: dict[str, Any]
    weblog_url: str | None = None


@dataclass(frozen=True, slots=True)
class BatchSubmissionResult:
    job_id: str | None
    submitted: bool


def _param_args(parameters: dict[str, Any]) -> list[str]:
    args: list[str] = []
    for name in sorted(parameters):
        value = parameters[name]
        if not _PARAM_NAME.match(name):
            raise InvalidParameterError(f"Invalid parameter name '{name}'")
        if name in RESERVED_PARAMS:
            raise InvalidParameterError(f"Parameter '{name}' is set by the platform")
        if value is None:
            continue
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, int | float | str):
            rendered = str(value)
        else:
            raise InvalidParameterError(f"Parameter '{name}' must be a string, number or boolean")
        args.extend([f"--{name}", rendered])
    return args


def validate_parameters(parameters: dict[str, Any]) -> None:
    """Raise ``InvalidParameterError`` if ``parameters`` cannot be passed to Nextflow."""
    _param_args(parameters)


def build_nextflow_command(launch: NextflowLaunch) -> list[str]:
    """The exact ``nextflow run`` argument list. No shell is involved."""
    if not _RUN_NAME.match(launch.run_name):
        raise InvalidParameterError(f"Invalid Nextflow run name '{launch.run_name}'")
    command = [
        "nextflow",
        "run",
        f"nf-core/{launch.pipeline_id}",
        "-r",
        launch.pipeline_version,
        "-name",
        launch.run_name,
        "-profile",
        settings.nextflow_profile,
        "-work-dir",
        launch.work_dir,
        "-ansi-log",
        "false",
    ]
    if settings.nextflow_config_uri:
        command.extend(["-c", settings.nextflow_config_uri])
    if launch.weblog_url:
        command.extend(["-with-weblog", launch.weblog_url])
    command.extend(["--input", launch.input_uri, "--outdir", launch.outdir_uri])
    command.extend(_param_args(launch.parameters))
    return command


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
    @property
    def enabled(self) -> bool:
        return get_batch_client() is not None

    def submit(self, launch: NextflowLaunch, *, workspace: str) -> BatchSubmissionResult:
        """
        Submit the Nextflow head job. When AWS Batch is disabled nothing is executed and
        ``submitted`` is False: the caller records the run as not submitted.
        """
        command = build_nextflow_command(launch)
        client = get_batch_client()
        if client is None:
            logger.info("AWS Batch disabled; run %s recorded but not submitted", launch.run_name)
            return BatchSubmissionResult(job_id=None, submitted=False)

        overrides: ContainerOverridesTypeDef = {
            "command": command,
            "environment": [{"name": "LABCHAIN_WORKSPACE", "value": workspace}],
        }
        response = client.submit_job(
            jobName=launch.run_name[:128],
            jobQueue=settings.aws_batch_job_queue,
            jobDefinition=settings.aws_batch_job_definition,
            containerOverrides=overrides,
            tags={
                "project": "labchain-biologics",
                "workspace": workspace,
                "pipeline": launch.pipeline_id,
            },
        )
        return BatchSubmissionResult(job_id=response["jobId"], submitted=True)

    def describe_job(self, job_id: str) -> dict[str, Any]:
        client = get_batch_client()
        if client is None:
            return {"jobId": job_id, "status": "UNKNOWN"}
        response = client.describe_jobs(jobs=[job_id])
        jobs = response.get("jobs", [])
        if not jobs:
            return {"jobId": job_id, "status": "NOT_FOUND"}
        job = jobs[0]
        return {
            "jobId": job.get("jobId", job_id),
            "status": job.get("status", "UNKNOWN"),
            "statusReason": job.get("statusReason"),
        }


batch_service = BatchService()
