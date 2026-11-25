"""Multi-step helpers: FASTQ upload, verified download, run waiting and log streaming."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import httpx
import pytest
from fakes import NOW, WORKSPACE, FakeServer, body_of, ok, run_json

from labchain import (
    APIConnectionError,
    ChecksumMismatchError,
    Client,
    ExecutionDisabledError,
    RunEvent,
    RunFailedError,
    RunTimeoutError,
)
from labchain.models import FastqVerificationStatus, JobStatus
from labchain.resources.runs import parse_sse

UPLOAD_URL = "http://storage.test/bucket/lab-west/fastq/reads.fastq.gz?X-Amz-Signature=sig"
READS = b"@r1\nACGT\n+\nIIII\n" * 100


def _fastq_json(fastq_id: str, status: str, md5: str) -> dict[str, object]:
    return {
        "id": fastq_id,
        "workspace": WORKSPACE,
        "filename": "reads.fastq.gz",
        "s3Key": "lab-west/fastq/reads.fastq.gz",
        "sizeBytes": len(READS),
        "expectedMd5": md5,
        "computedMd5": md5,
        "verificationStatus": status,
        "createdAt": NOW,
    }


def _serve_fastq(server: FakeServer, verify_status: str) -> str:
    fastq_id = str(uuid.uuid4())
    md5 = hashlib.md5(READS).hexdigest()
    registration = {**_fastq_json(fastq_id, "pending", md5), "uploadUrl": UPLOAD_URL}
    server.on("POST", "/api/v1/fastq/register", ok(registration, 201))
    server.on("PUT", "/bucket/lab-west/fastq/reads.fastq.gz", ok(None))
    verification = {
        "id": fastq_id,
        "expectedMd5": md5,
        "computedMd5": md5 if verify_status == "verified" else "0" * 32,
        "verificationStatus": verify_status,
    }
    server.on("POST", f"/api/v1/fastq/{fastq_id}/verify", ok(verification))
    server.on("GET", f"/api/v1/fastq/{fastq_id}", ok(_fastq_json(fastq_id, verify_status, md5)))
    return fastq_id


@pytest.fixture
def reads(tmp_path: Path) -> Path:
    path = tmp_path / "reads.fastq.gz"
    path.write_bytes(READS)
    return path


def test_upload_registers_puts_and_verifies(
    client: Client, server: FakeServer, reads: Path
) -> None:
    sample_id = uuid.uuid4()
    fastq_id = _serve_fastq(server, "verified")

    fastq = client.fastq.upload(reads, sample_id=sample_id, read_pair="R1")

    assert str(fastq.id) == fastq_id
    assert fastq.verification_status is FastqVerificationStatus.verified
    registered = body_of(server.last("POST", "/api/v1/fastq/register"))
    assert registered == {
        "filename": "reads.fastq.gz",
        "sizeBytes": len(READS),
        "expectedMd5": hashlib.md5(READS).hexdigest(),
        "sampleId": str(sample_id),
        "sequencingRunId": None,
        "readPair": "R1",
        "s3Key": None,
    }
    put = server.last("PUT", "/bucket/lab-west/fastq/reads.fastq.gz")
    assert put.content == READS
    assert put.headers["Content-Type"] == "application/gzip"
    assert put.headers["Content-Length"] == str(len(READS))
    # The signed URL is the credential: the API token and workspace must not leak to storage.
    assert "Authorization" not in put.headers
    assert "X-LabChain-Workspace" not in put.headers
    assert [r.method for r in server.requests] == ["POST", "PUT", "POST", "GET"]


def test_upload_raises_when_server_finds_a_mismatch(
    client: Client, server: FakeServer, reads: Path
) -> None:
    _serve_fastq(server, "mismatch")
    with pytest.raises(ChecksumMismatchError, match="mismatch"):
        client.fastq.upload(reads)


def test_upload_refuses_a_file_that_differs_from_the_manifest(
    client: Client, server: FakeServer, reads: Path
) -> None:
    with pytest.raises(ChecksumMismatchError, match="nothing was uploaded"):
        client.fastq.upload(reads, expected_md5="f" * 32)
    assert server.requests == []


def test_storage_rejection_does_not_leak_the_signed_url(
    client: Client, server: FakeServer, reads: Path
) -> None:
    _serve_fastq(server, "verified")
    server.on(
        "PUT",
        "/bucket/lab-west/fastq/reads.fastq.gz",
        httpx.Response(403, text="<Error><Code>SignatureDoesNotMatch</Code></Error>"),
    )
    with pytest.raises(APIConnectionError) as exc_info:
        client.fastq.upload(reads)
    assert "SignatureDoesNotMatch" in str(exc_info.value)
    assert "X-Amz-Signature" not in str(exc_info.value)


def _serve_result(server: FakeServer, content: bytes, md5: str | None) -> str:
    output_id = str(uuid.uuid4())
    server.on(
        "GET",
        f"/api/v1/results/{output_id}/download",
        ok(
            {
                "id": output_id,
                "fileType": "vcf",
                "filename": "variants.vcf.gz",
                "downloadUrl": "http://storage.test/bucket/out/variants.vcf.gz?X-Amz-Signature=s",
                "expiresIn": 3600,
                "md5": md5,
            }
        ),
    )
    server.on("GET", "/bucket/out/variants.vcf.gz", httpx.Response(200, content=content))
    return output_id


def test_download_into_directory_checks_md5(
    client: Client, server: FakeServer, tmp_path: Path
) -> None:
    content = b"##fileformat=VCFv4.2\n"
    output_id = _serve_result(server, content, hashlib.md5(content).hexdigest())

    path = client.results.download(output_id, tmp_path)

    assert path == tmp_path / "variants.vcf.gz"
    assert path.read_bytes() == content
    storage_get = server.last("GET", "/bucket/out/variants.vcf.gz")
    assert "Authorization" not in storage_get.headers


def test_download_mismatch_leaves_nothing_behind(
    client: Client, server: FakeServer, tmp_path: Path
) -> None:
    output_id = _serve_result(server, b"corrupted", "0" * 32)
    target = tmp_path / "variants.vcf.gz"

    with pytest.raises(ChecksumMismatchError):
        client.results.download(output_id, target)
    assert list(tmp_path.iterdir()) == []


def test_wait_polls_until_success(
    client: Client, server: FakeServer, no_sleep: list[float]
) -> None:
    run_id = str(uuid.uuid4())
    server.on(
        "GET",
        f"/api/v1/runs/{run_id}",
        ok(run_json(id=run_id, status="submitted")),
        ok(run_json(id=run_id, status="running")),
        ok(run_json(id=run_id, status="succeeded")),
    )
    run = client.runs.wait(run_id, poll_interval=5)
    assert run.status is JobStatus.succeeded
    assert no_sleep == [5, 5]


def test_wait_refuses_a_run_that_will_never_execute(client: Client, server: FakeServer) -> None:
    run_id = str(uuid.uuid4())
    not_submitted = run_json(
        id=run_id, status="pending", executionSubmitted=False, awsBatchJobId=None
    )
    server.on("GET", f"/api/v1/runs/{run_id}", ok(not_submitted))
    with pytest.raises(ExecutionDisabledError, match="disabled"):
        client.runs.wait(run_id)
    assert len(server.requests) == 1


def test_wait_raises_on_failure_with_server_message(client: Client, server: FakeServer) -> None:
    run_id = str(uuid.uuid4())
    failed = run_json(id=run_id, status="failed", progress={"errorMessage": "STAR exited 137"})
    server.on("GET", f"/api/v1/runs/{run_id}", ok(failed))

    with pytest.raises(RunFailedError, match="STAR exited 137"):
        client.runs.wait(run_id)
    assert client.runs.wait(run_id, raise_on_failure=False).status is JobStatus.failed


def test_wait_times_out(client: Client, server: FakeServer) -> None:
    run_id = str(uuid.uuid4())
    server.on("GET", f"/api/v1/runs/{run_id}", ok(run_json(id=run_id, status="running")))
    with pytest.raises(RunTimeoutError):
        client.runs.wait(run_id, timeout=10, poll_interval=15)


def test_launch_sends_run_request(client: Client, server: FakeServer) -> None:
    sample_id = uuid.uuid4()
    server.on("POST", "/api/v1/runs", ok(run_json(), 201))
    run = client.runs.launch("rnaseq", sample_ids=[sample_id], parameters={"aligner": "star"})
    assert run.execution_submitted is True
    assert body_of(server.last("POST", "/api/v1/runs")) == {
        "pipelineId": "rnaseq",
        "pipelineVersion": "latest",
        "sampleIds": [str(sample_id)],
        "sequencingRunId": None,
        "parameters": {"aligner": "star"},
    }


STREAM = (
    ": ping\r\n\r\n"
    "event: log\r\ndata: 2026-11-25T12:00:00Z Samplesheet written\r\nid: 0\r\n\r\n"
    "event: status\r\ndata: running\r\n\r\n"
    "event: log\r\ndata: line one\r\ndata: line two\r\nid: 1\r\n\r\n"
    "event: end\r\ndata: succeeded\r\n\r\n"
    "event: log\r\ndata: after end is ignored\r\n\r\n"
)


def test_stream_logs_yields_events_until_end(client: Client, server: FakeServer) -> None:
    run_id = str(uuid.uuid4())
    server.on(
        "GET",
        f"/api/v1/runs/{run_id}/logs/stream",
        httpx.Response(200, text=STREAM, headers={"Content-Type": "text/event-stream"}),
    )
    events = list(client.runs.stream_logs(run_id))

    assert events == [
        RunEvent("log", "2026-11-25T12:00:00Z Samplesheet written", 0),
        RunEvent("status", "running"),
        RunEvent("log", "line one\nline two", 1),
        RunEvent("end", "succeeded"),
    ]
    request = server.last("GET", f"/api/v1/runs/{run_id}/logs/stream")
    assert request.headers["Accept"] == "text/event-stream"


def test_parse_sse_ignores_unknown_events() -> None:
    lines = ["event: custom", "data: x", "", "event: end", "data: failed", ""]
    assert list(parse_sse(lines)) == [RunEvent("end", "failed")]


def test_logs_cursor(client: Client, server: FakeServer) -> None:
    run_id = str(uuid.uuid4())
    line = {"index": 4, "timestamp": NOW, "message": "done"}
    server.on("GET", f"/api/v1/runs/{run_id}/logs", ok([line]))
    [log] = client.runs.logs(run_id, after=3)
    assert log.index == 4
    assert server.last("GET", f"/api/v1/runs/{run_id}/logs").url.params["after"] == "3"
