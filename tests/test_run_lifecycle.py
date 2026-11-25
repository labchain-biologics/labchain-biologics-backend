"""Unit tests for run lifecycle helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.models.pipeline import OutputFileType, PipelineJob
from app.services import run_lifecycle


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("ws/results/1/multiqc/multiqc_report.html", OutputFileType.multiqc),
        ("ws/results/1/vc/sample.vcf.gz", OutputFileType.vcf),
        ("ws/results/1/vc/sample.VCF", OutputFileType.vcf),
        ("ws/results/1/pre/sample.cram", OutputFileType.bam),
        ("ws/results/1/pre/sample.bam", OutputFileType.bam),
        ("ws/results/1/pre/sample.bam.bai", OutputFileType.other),
        ("ws/results/1/pipeline_info/execution_trace.txt", OutputFileType.other),
    ],
)
def test_classify_output(key: str, expected: OutputFileType) -> None:
    assert run_lifecycle.classify_output(key) == expected


def test_weblog_token_is_per_run_and_verifiable() -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    token = run_lifecycle.weblog_token(first)
    assert run_lifecycle.verify_weblog_token(first, token)
    assert not run_lifecycle.verify_weblog_token(second, token)
    assert not run_lifecycle.verify_weblog_token(first, "0" * 64)


def test_weblog_url_requires_public_api_url(monkeypatch: pytest.MonkeyPatch) -> None:
    job_id = uuid.uuid4()
    monkeypatch.setattr(run_lifecycle.settings, "public_api_url", None)
    assert run_lifecycle.weblog_url(job_id) is None
    monkeypatch.setattr(run_lifecycle.settings, "public_api_url", "https://api.example.org/")
    assert run_lifecycle.weblog_url(job_id) == (
        f"https://api.example.org/api/v1/runs/{job_id}/events"
        f"?token={run_lifecycle.weblog_token(job_id)}"
    )


def test_append_log_writes_timestamped_lines() -> None:
    job = PipelineJob(log_buffer="")
    run_lifecycle.append_log(job, "first", datetime(2026, 11, 25, 10, tzinfo=UTC))
    run_lifecycle.append_log(job, "second")
    lines = job.log_buffer.splitlines()
    assert lines[0] == "[2026-11-25T10:00:00+00:00] first"
    assert lines[1].endswith("] second")
