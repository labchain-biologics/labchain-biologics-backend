"""Unit tests for Nextflow command construction and AWS Batch submission."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.services import batch
from app.services.batch import (
    BatchService,
    InvalidParameterError,
    NextflowLaunch,
    build_nextflow_command,
    validate_parameters,
)


def _launch(**overrides: Any) -> NextflowLaunch:
    values: dict[str, Any] = {
        "pipeline_id": "rnaseq",
        "pipeline_version": "3.14.0",
        "run_name": "lc-rnaseq-abc123",
        "work_dir": "s3://bucket/work/lab-a/1",
        "input_uri": "s3://bucket/lab-a/runs/1/samplesheet.csv",
        "outdir_uri": "s3://bucket/lab-a/results/1",
        "parameters": {"aligner": "star_salmon", "skip_qc": True, "min_reads": 10, "x": None},
        "weblog_url": None,
    }
    values.update(overrides)
    return NextflowLaunch(**values)


def test_command_has_pipeline_revision_io_and_typed_params() -> None:
    command = build_nextflow_command(_launch())
    assert command[:5] == ["nextflow", "run", "nf-core/rnaseq", "-r", "3.14.0"]
    joined = " ".join(command)
    assert "-name lc-rnaseq-abc123" in joined
    assert "-work-dir s3://bucket/work/lab-a/1" in joined
    assert "--input s3://bucket/lab-a/runs/1/samplesheet.csv" in joined
    assert "--outdir s3://bucket/lab-a/results/1" in joined
    assert "--aligner star_salmon" in joined
    assert "--skip_qc true" in joined
    assert "--min_reads 10" in joined
    assert "--x" not in command  # None values are omitted
    assert "-with-weblog" not in command


def test_command_includes_weblog_and_custom_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(batch.settings, "nextflow_config_uri", "s3://bucket/conf/awsbatch.config")
    monkeypatch.setattr(batch.settings, "nextflow_profile", "awsbatch")
    command = build_nextflow_command(_launch(weblog_url="https://api/x?token=t"))
    assert command[command.index("-c") + 1] == "s3://bucket/conf/awsbatch.config"
    assert command[command.index("-profile") + 1] == "awsbatch"
    assert command[command.index("-with-weblog") + 1] == "https://api/x?token=t"


@pytest.mark.parametrize(
    "parameters",
    [
        {"outdir": "s3://elsewhere"},
        {"input": "s3://other.csv"},
        {"--flag": "x"},
        {"name with space": "x"},
        {"tools": ["a", "b"]},
        {"cfg": {"a": 1}},
    ],
)
def test_invalid_parameters_are_rejected(parameters: dict[str, Any]) -> None:
    with pytest.raises(InvalidParameterError):
        validate_parameters(parameters)


def test_parameter_values_are_single_arguments() -> None:
    """Values are passed as one argv element each: no shell, no word splitting."""
    command = build_nextflow_command(_launch(parameters={"genome": "GRCh38; rm -rf /"}))
    assert command[command.index("--genome") + 1] == "GRCh38; rm -rf /"


def test_invalid_run_name_rejected() -> None:
    with pytest.raises(InvalidParameterError):
        build_nextflow_command(_launch(run_name="Bad Name"))


def test_submit_does_nothing_when_batch_disabled() -> None:
    with patch("app.services.batch.get_batch_client", return_value=None):
        result = BatchService().submit(_launch(), workspace="lab-a")
    assert result.submitted is False
    assert result.job_id is None


def test_submit_sends_full_command_to_aws_batch() -> None:
    client = MagicMock()
    client.submit_job.return_value = {"jobId": "batch-job-123"}
    with patch("app.services.batch.get_batch_client", return_value=client):
        result = BatchService().submit(_launch(), workspace="lab-a")

    assert result.submitted is True
    assert result.job_id == "batch-job-123"
    kwargs = client.submit_job.call_args.kwargs
    assert kwargs["jobName"] == "lc-rnaseq-abc123"
    assert kwargs["containerOverrides"]["command"] == build_nextflow_command(_launch())
    assert kwargs["tags"]["workspace"] == "lab-a"


def test_describe_job_not_found() -> None:
    client = MagicMock()
    client.describe_jobs.return_value = {"jobs": []}
    with patch("app.services.batch.get_batch_client", return_value=client):
        info = BatchService().describe_job("real-job")
    assert info["status"] == "NOT_FOUND"


def test_describe_job_returns_status() -> None:
    client = MagicMock()
    client.describe_jobs.return_value = {
        "jobs": [{"jobId": "real-job", "status": "SUCCEEDED", "statusReason": "done"}]
    }
    with patch("app.services.batch.get_batch_client", return_value=client):
        info = BatchService().describe_job("real-job")
    assert info["status"] == "SUCCEEDED"
    assert info["statusReason"] == "done"
