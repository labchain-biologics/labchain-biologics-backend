"""Unit tests for AWS Batch / Nextflow submission hooks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.batch import BatchService


def test_submit_nextflow_job_simulates_when_batch_disabled() -> None:
    service = BatchService()
    with patch("app.services.batch.get_batch_client", return_value=None):
        result = service.submit_nextflow_job(
            pipeline_id="rnaseq",
            pipeline_version="3.14.0",
            parameters={"aligner": "star_salmon"},
            workspace="lab-a",
            run_name="vc-rnaseq-demo",
        )

    assert result.simulated is True
    assert result.job_id.startswith("sim-")
    assert result.job_name == "vc-rnaseq-demo"
    assert result.nextflow_run_name == "vc-rnaseq-demo"
    assert result.work_dir.endswith("/lab-a/vc-rnaseq-demo")


def test_submit_nextflow_job_calls_aws_batch_when_enabled() -> None:
    client = MagicMock()
    client.submit_job.return_value = {"jobId": "batch-job-123"}
    service = BatchService()

    with patch("app.services.batch.get_batch_client", return_value=client):
        result = service.submit_nextflow_job(
            pipeline_id="sarek",
            pipeline_version="3.4.0",
            parameters={"genome": "GATK.GRCh38"},
            workspace="default",
            run_name="vc-sarek-1",
        )

    assert result.simulated is False
    assert result.job_id == "batch-job-123"
    client.submit_job.assert_called_once()
    call_kwargs = client.submit_job.call_args.kwargs
    assert call_kwargs["jobName"] == "vc-sarek-1"
    assert "nf-core/sarek" in call_kwargs["containerOverrides"]["command"]


def test_describe_job_simulated() -> None:
    service = BatchService()
    with patch("app.services.batch.get_batch_client", return_value=None):
        info = service.describe_job("sim-abc123")
    assert info["status"] == "RUNNING"
    assert info["simulated"] is True


def test_describe_job_not_found() -> None:
    client = MagicMock()
    client.describe_jobs.return_value = {"jobs": []}
    service = BatchService()
    with patch("app.services.batch.get_batch_client", return_value=client):
        info = service.describe_job("real-job")
    assert info["status"] == "NOT_FOUND"
    assert info["simulated"] is False


def test_describe_job_returns_status() -> None:
    client = MagicMock()
    client.describe_jobs.return_value = {
        "jobs": [{"jobId": "real-job", "status": "SUCCEEDED", "statusReason": "done"}]
    }
    service = BatchService()
    with patch("app.services.batch.get_batch_client", return_value=client):
        info = service.describe_job("real-job")
    assert info["status"] == "SUCCEEDED"
    assert info["statusReason"] == "done"
