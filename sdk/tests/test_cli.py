"""The ``labchain`` command, against the scripted fake server (no network)."""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import BASE_URL, TOKEN, WORKSPACE, FakeServer, body_of, ok, run_json, sample_json
from test_workflows import READS, STREAM, _serve_fastq, _serve_result
from typer.testing import CliRunner, Result

from labchain import Client, __version__
from labchain.cli import app as cli_module
from labchain.cli import main
from labchain.cli.app import app, infer_read_pair, parse_param


@pytest.fixture
def invoke(server: FakeServer, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Run ``labchain`` with LABCHAIN_* set and every Client wired to the fake server."""

    class FakeClient(Client):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(server)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(cli_module, "Client", FakeClient)
    env = {"LABCHAIN_URL": BASE_URL, "LABCHAIN_TOKEN": TOKEN, "LABCHAIN_WORKSPACE": WORKSPACE}
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    runner = CliRunner()

    def run(*args: str, input: str | None = None) -> Result:
        return runner.invoke(app, list(args), input=input)

    yield run


def test_version_needs_no_server(invoke: Any, server: FakeServer) -> None:
    result = invoke("version")
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
    assert server.requests == []


def test_token_is_not_a_command_line_option(invoke: Any) -> None:
    result = invoke("--help")
    assert result.exit_code == 0
    assert "--token" not in result.stdout
    assert "LABCHAIN_URL" in result.stdout


def test_missing_cli_extra_gets_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(sys.modules, "typer", None)  # makes `import typer` fail
    monkeypatch.delitem(sys.modules, "labchain.cli.app")
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    assert 'pip install "labchain-biologics-sdk[cli]"' in capsys.readouterr().err


def test_samples_list_json_uses_api_field_names(invoke: Any, server: FakeServer) -> None:
    server.on("GET", "/api/v1/samples", ok([sample_json(sampleCode="RNA-1")]))

    result = invoke("--json", "samples", "list", "--status", "registered", "--limit", "5")

    assert result.exit_code == 0, result.output
    [sample] = json.loads(result.stdout)
    assert sample["sampleCode"] == "RNA-1"
    request = server.last("GET", "/api/v1/samples")
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.headers["X-LabChain-Workspace"] == WORKSPACE
    assert request.url.params["status"] == "registered"
    assert request.url.params["limit"] == "5"


def test_samples_list_table_and_all_pages(invoke: Any, server: FakeServer) -> None:
    page = [sample_json(sampleCode=f"S-{i}") for i in range(1000)]
    server.on("GET", "/api/v1/samples", ok(page), ok([sample_json(sampleCode="LAST")]))

    result = invoke("samples", "list", "--all")

    assert result.exit_code == 0, result.output
    assert "CODE" in result.stdout and "LAST" in result.stdout
    assert [r.url.params["offset"] for r in server.requests] == ["0", "1000"]


def test_workspace_option_overrides_environment(invoke: Any, server: FakeServer) -> None:
    server.on("GET", "/api/v1/runs", ok([]))
    assert invoke("-w", "lab-east", "runs", "list").exit_code == 0
    assert server.last("GET", "/api/v1/runs").headers["X-LabChain-Workspace"] == "lab-east"


def test_api_error_is_one_line_on_stderr_with_status_1(invoke: Any, server: FakeServer) -> None:
    server.on("POST", "/api/v1/runs", ok({"detail": "Requires bioinformatics_lead"}, 403))

    result = invoke("runs", "launch", "rnaseq", "--sample", str(uuid.uuid4()))

    assert result.exit_code == 1
    assert "error:" in result.stderr and "bioinformatics_lead" in result.stderr
    assert "Traceback" not in result.output
    assert TOKEN not in result.output


def test_invalid_choice_is_a_usage_error_without_a_request(invoke: Any, server: FakeServer) -> None:
    result = invoke("members", "add", "new@lab.test", "--role", "admin")
    assert result.exit_code == 2
    assert "lab_technician" in result.stderr  # the valid choices are listed
    assert server.requests == []


def test_local_validation_error_is_reported_without_a_request(
    invoke: Any, server: FakeServer
) -> None:
    server.on("POST", "/api/v1/auth/login", ok({"accessToken": "jwt", "expiresIn": 3600}))
    result = invoke("token", "create", "", "--email", "lead@lab.test", input="pw\n")
    assert result.exit_code == 1
    assert "error:" in result.stderr and "invalid argument" in result.stderr
    assert [r.url.path for r in server.requests] == ["/api/v1/auth/login"]


def test_token_create_prompts_for_the_password(invoke: Any, server: FakeServer) -> None:
    server.on("POST", "/api/v1/auth/login", ok({"accessToken": "jwt", "expiresIn": 3600}))
    created = {
        "id": str(uuid.uuid4()),
        "name": "ci",
        "tokenPrefix": "lcb_pat_abcd1234",
        "createdAt": "2026-11-26T09:00:00Z",
        "expiresAt": "2027-02-24T09:00:00Z",
        "token": "lcb_pat_abcd1234-the-secret",
    }
    server.on("POST", "/api/v1/auth/tokens", ok(created, 201))

    result = invoke("token", "create", "ci", "--email", "lead@lab.test", input="s3cret\n")

    assert result.exit_code == 0, result.output
    # The secret alone on stdout, so `export LABCHAIN_TOKEN=$(labchain token create ...)` works.
    assert result.stdout.strip() == "lcb_pat_abcd1234-the-secret"
    assert "Password" in result.stderr
    assert "s3cret" not in result.output
    assert body_of(server.last("POST", "/api/v1/auth/login")) == {
        "email": "lead@lab.test",
        "password": "s3cret",
    }
    assert server.last("POST", "/api/v1/auth/tokens").headers["Authorization"] == "Bearer jwt"


def test_fastq_upload_infers_the_read_pair(invoke: Any, server: FakeServer, tmp_path: Path) -> None:
    path = tmp_path / "S1_L001_R2_001.fastq.gz"
    path.write_bytes(READS)
    _serve_fastq(server, "verified")
    sample_id = str(uuid.uuid4())

    result = invoke("fastq", "upload", str(path), "--sample", sample_id)

    assert result.exit_code == 0, result.output
    registered = body_of(server.last("POST", "/api/v1/fastq/register"))
    assert registered["readPair"] == "R2"
    assert registered["sampleId"] == sample_id
    assert registered["expectedMd5"] == hashlib.md5(READS).hexdigest()
    assert "verified S1_L001_R2_001.fastq.gz" in result.stderr


def test_fastq_upload_mismatch_fails(invoke: Any, server: FakeServer, tmp_path: Path) -> None:
    path = tmp_path / "reads.fastq.gz"
    path.write_bytes(READS)
    _serve_fastq(server, "mismatch")
    result = invoke("fastq", "upload", str(path))
    assert result.exit_code == 1
    assert "mismatch" in result.stderr


@pytest.mark.parametrize(
    ("name", "pair"),
    [
        ("S1_L001_R1_001.fastq.gz", "R1"),
        ("sample.R2.fastq.gz", "R2"),
        ("sample-R1.fq.gz", "R1"),
        ("RNA_R10_x.fastq.gz", None),
        ("reads.fastq.gz", None),
    ],
)
def test_infer_read_pair(name: str, pair: str | None) -> None:
    assert infer_read_pair(Path(name)) == pair


def test_parse_param_reads_json_values() -> None:
    assert parse_param("skip_qc=true") == ("skip_qc", True)
    assert parse_param("max_cpus=8") == ("max_cpus", 8)
    assert parse_param("genome=GRCh38") == ("genome", "GRCh38")
    assert parse_param("tools=mutect2,strelka") == ("tools", "mutect2,strelka")


def test_launch_sends_parameters_and_warns_when_not_submitted(
    invoke: Any, server: FakeServer, tmp_path: Path
) -> None:
    params_file = tmp_path / "params.json"
    params_file.write_text(json.dumps({"genome": "GRCh38", "max_cpus": 4}), encoding="utf-8")
    pending = run_json(status="pending", executionSubmitted=False, awsBatchJobId=None)
    server.on("POST", "/api/v1/runs", ok(pending, 201))
    sample_id = str(uuid.uuid4())

    result = invoke(
        "runs",
        "launch",
        "rnaseq",
        "-s",
        sample_id,
        "--params-file",
        str(params_file),
        "-p",
        "max_cpus=8",
        "-p",
        "skip_qc=true",
    )

    assert result.exit_code == 0, result.output
    assert body_of(server.last("POST", "/api/v1/runs"))["parameters"] == {
        "genome": "GRCh38",
        "max_cpus": 8,
        "skip_qc": True,
    }
    assert "not submitted" in result.stderr


def test_launch_and_wait_fails_when_execution_is_disabled(invoke: Any, server: FakeServer) -> None:
    pending = run_json(status="pending", executionSubmitted=False, awsBatchJobId=None)
    server.on("POST", "/api/v1/runs", ok(pending, 201))
    server.on("GET", f"/api/v1/runs/{pending['id']}", ok(pending))

    result = invoke("runs", "launch", "rnaseq", "-s", str(uuid.uuid4()), "--wait")

    assert result.exit_code == 1
    assert "disabled" in result.stderr


def test_runs_wait_exit_status_follows_the_outcome(invoke: Any, server: FakeServer) -> None:
    ok_id, failed_id = str(uuid.uuid4()), str(uuid.uuid4())
    server.on("GET", f"/api/v1/runs/{ok_id}", ok(run_json(id=ok_id, status="succeeded")))
    failed = run_json(id=failed_id, status="failed", progress={"errorMessage": "OOM"})
    server.on("GET", f"/api/v1/runs/{failed_id}", ok(failed))

    assert invoke("runs", "wait", ok_id).exit_code == 0
    result = invoke("runs", "wait", failed_id)
    assert result.exit_code == 1
    assert "OOM" in result.stderr


def test_runs_logs_follow_prints_log_lines(invoke: Any, server: FakeServer) -> None:
    run_id = str(uuid.uuid4())
    server.on(
        "GET",
        f"/api/v1/runs/{run_id}/logs/stream",
        httpx.Response(200, text=STREAM, headers={"Content-Type": "text/event-stream"}),
    )
    result = invoke("runs", "logs", run_id, "--follow")

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == [
        "2026-11-25T12:00:00Z Samplesheet written",
        "line one",
        "line two",
    ]
    assert "status: running" in result.stderr


def test_results_download_every_output_of_a_run(
    invoke: Any, server: FakeServer, tmp_path: Path
) -> None:
    content = b"##fileformat=VCFv4.2\n"
    output_id = _serve_result(server, content, hashlib.md5(content).hexdigest())
    run_id = str(uuid.uuid4())
    listing = {
        "id": output_id,
        "fileType": "vcf",
        "filename": "variants.vcf.gz",
        "s3Key": "lab-west/results/x/variants.vcf.gz",
        "sizeBytes": len(content),
        "createdAt": "2026-11-26T09:00:00Z",
    }
    server.on("GET", f"/api/v1/results/runs/{run_id}", ok([listing]))
    dest = tmp_path / "out"

    result = invoke("results", "download", "--run", run_id, "--dest", str(dest))

    assert result.exit_code == 0, result.output
    assert (dest / "variants.vcf.gz").read_bytes() == content


def test_json_output_never_prints_signed_urls(invoke: Any, server: FakeServer) -> None:
    output = {
        "id": str(uuid.uuid4()),
        "fileType": "bam",
        "filename": "x.bam",
        "s3Key": "k",
        "sizeBytes": 1,
        "downloadUrl": "https://storage.test/x.bam?X-Amz-Signature=secret",
        "createdAt": "2026-11-26T09:00:00Z",
    }
    server.on("GET", "/api/v1/results", ok([output]))

    result = invoke("--json", "results", "list", "--type", "bam")

    assert result.exit_code == 0, result.output
    assert "X-Amz-Signature" not in result.stdout
    assert json.loads(result.stdout)[0]["filename"] == "x.bam"
