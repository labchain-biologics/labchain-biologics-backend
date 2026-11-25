"""Run execution: samplesheet, submission, Nextflow weblog lifecycle, Batch reconciliation."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.audit import AuditLog
from app.models.pipeline import JobStatus, PipelineJob
from app.models.user import Role, User
from app.models.workspace import Workspace
from app.services import run_lifecycle
from app.services.batch import BatchSubmissionResult, NextflowLaunch, batch_service
from tests.integration.conftest import FakeS3

MakeUser = Callable[..., Awaitable[User]]
MakeWorkspace = Callable[..., Awaitable[Workspace]]
Login = Callable[[str], Awaitable[dict[str, str]]]
Headers = dict[str, str]


async def _setup(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    fake_s3: FakeS3,
    *,
    sample_type: str = "tumor",
) -> tuple[Headers, dict[str, Any]]:
    """A lead in workspace lab-west and one sample with a verified R1/R2 pair."""
    lead = await make_user("lead@lab.io")
    await make_workspace("lab-west", {lead.id: Role.bioinformatics_lead})
    headers = {**(await login("lead@lab.io")), "X-LabChain-Workspace": "lab-west"}
    sample = (
        await client.post(
            "/api/v1/samples",
            json={
                "sampleCode": "SMP 001",
                "modality": "genomics",
                "assay": "exome",
                "sampleType": sample_type,
                "patientId": "PT-1",
            },
            headers=headers,
        )
    ).json()
    for pair in ("R1", "R2"):
        registered = (
            await client.post(
                "/api/v1/fastq/register",
                json={
                    "filename": f"smp_{pair}.fastq.gz",
                    "sampleId": sample["id"],
                    "readPair": pair,
                },
                headers=headers,
            )
        ).json()
        fake_s3.objects[registered["s3Key"]] = f"reads {pair}".encode()
        verified = await client.post(f"/api/v1/fastq/{registered['id']}/verify", headers=headers)
        assert verified.json()["verificationStatus"] == "verified"
    return headers, sample


@pytest.fixture
def submitted(monkeypatch: pytest.MonkeyPatch) -> list[NextflowLaunch]:
    """AWS Batch enabled: capture launches instead of calling AWS."""
    launches: list[NextflowLaunch] = []

    def submit(launch: NextflowLaunch, *, workspace: str) -> BatchSubmissionResult:
        launches.append(launch)
        return BatchSubmissionResult(job_id="batch-job-1", submitted=True)

    monkeypatch.setattr(batch_service, "submit", submit)
    return launches


async def test_launch_with_execution_disabled_records_but_does_not_submit(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    fake_s3: FakeS3,
) -> None:
    headers, sample = await _setup(client, make_user, make_workspace, login, fake_s3)

    response = await client.post(
        "/api/v1/runs", json={"pipelineId": "sarek", "sampleIds": [sample["id"]]}, headers=headers
    )

    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "pending"
    assert run["awsBatchJobId"] is None
    assert run["outputFiles"] == []
    assert run["outputDir"] == f"s3://test-bucket/lab-west/results/{run['id']}"

    sheet_key = f"lab-west/runs/{run['id']}/samplesheet.csv"
    assert run["samplesheetUri"] == f"s3://test-bucket/{sheet_key}"
    lines = fake_s3.objects[sheet_key].decode().splitlines()
    assert lines[0] == "patient,sex,status,sample,lane,fastq_1,fastq_2"
    patient, _, status, name, _, fastq_1, fastq_2 = lines[1].split(",")
    assert (patient, status, name) == ("PT-1", "1", "SMP_001")
    assert fastq_1.endswith("smp_R1.fastq.gz") and fastq_2.endswith("smp_R2.fastq.gz")

    logs = (await client.get(f"/api/v1/runs/{run['id']}/logs", headers=headers)).json()
    messages = [line["message"] for line in logs]
    assert any(m.startswith("Command: nextflow run nf-core/sarek -r 3.4.4") for m in messages)
    assert any("Not submitted" in m for m in messages)

    still = await client.get(f"/api/v1/samples/{sample['id']}", headers=headers)
    assert still.json()["status"] == "fastq_received"


async def test_full_lifecycle_through_weblog_events(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    fake_s3: FakeS3,
    submitted: list[NextflowLaunch],
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    monkeypatch.setattr(run_lifecycle.settings, "public_api_url", "https://api.test")
    headers, sample = await _setup(client, make_user, make_workspace, login, fake_s3)

    run = (
        await client.post(
            "/api/v1/runs",
            json={
                "pipelineId": "sarek",
                "sampleIds": [sample["id"]],
                "parameters": {"tools": "mutect2", "skip_qc": True},
            },
            headers=headers,
        )
    ).json()
    assert run["status"] == "submitted"
    assert run["awsBatchJobId"] == "batch-job-1"
    launch = submitted[0]
    assert launch.parameters["tools"] == "mutect2"
    assert launch.weblog_url is not None and launch.weblog_url.startswith(
        f"https://api.test/api/v1/runs/{run['id']}/events?token="
    )
    logs = (await client.get(f"/api/v1/runs/{run['id']}/logs", headers=headers)).json()
    assert all(run_lifecycle.weblog_token(launch_id(run)) not in line["message"] for line in logs)
    assert (await client.get(f"/api/v1/samples/{sample['id']}", headers=headers)).json()[
        "status"
    ] == "processing"

    events_url = launch.weblog_url.removeprefix("https://api.test")
    bad = await client.post(
        f"/api/v1/runs/{run['id']}/events?token={'0' * 64}", json={"event": "started"}
    )
    assert bad.status_code == 404

    for event in (
        {"event": "started", "runName": launch.run_name, "utcTime": "2026-11-25T10:00:00Z"},
        {"event": "process_submitted", "trace": {"name": "FASTQC (1)", "status": "SUBMITTED"}},
        {"event": "process_started", "trace": {"name": "FASTQC (1)", "status": "RUNNING"}},
        {"event": "process_completed", "trace": {"name": "FASTQC (1)", "status": "COMPLETED"}},
    ):
        assert (await client.post(events_url, json=event)).status_code == 204

    running = (await client.get(f"/api/v1/runs/{run['id']}", headers=headers)).json()
    assert running["status"] == "running"
    assert running["progress"]["processesCompleted"] == 1
    assert running["progress"]["currentProcess"] == "FASTQC (1)"

    results_prefix = f"lab-west/results/{run['id']}/"
    fake_s3.objects[results_prefix + "multiqc/multiqc_report.html"] = b"<html/>"
    fake_s3.objects[results_prefix + "variant_calling/mutect2/smp.vcf.gz"] = b"vcf"
    fake_s3.objects[results_prefix + "preprocessing/smp.cram"] = b"cram"
    completed = await client.post(
        events_url,
        json={
            "event": "completed",
            "utcTime": "2026-11-25T11:00:00Z",
            "metadata": {"workflow": {"success": True}},
        },
    )
    assert completed.status_code == 204

    done = (await client.get(f"/api/v1/runs/{run['id']}", headers=headers)).json()
    assert done["status"] == "succeeded"
    assert done["finishedAt"].startswith("2026-11-25T11:00:00")
    types = sorted((f["fileType"], f["filename"]) for f in done["outputFiles"])
    assert types == [
        ("bam", "smp.cram"),
        ("multiqc", "multiqc_report.html"),
        ("vcf", "smp.vcf.gz"),
    ]
    assert (await client.get(f"/api/v1/samples/{sample['id']}", headers=headers)).json()[
        "status"
    ] == "completed"

    # A late duplicate event does not change a finished run.
    again = await client.post(
        events_url, json={"event": "completed", "metadata": {"workflow": {"success": False}}}
    )
    assert again.status_code == 204
    final = (await client.get(f"/api/v1/runs/{run['id']}", headers=headers)).json()
    assert final["status"] == "succeeded"
    assert len(final["outputFiles"]) == 3

    async with session_factory() as session:
        changes = (
            await session.execute(
                select(AuditLog.after_state).where(
                    AuditLog.entity_id == run["id"], AuditLog.action == "status_change"
                )
            )
        ).scalars()
        assert [c["status"] for c in changes if c] == ["running", "succeeded"]


def launch_id(run: dict[str, Any]) -> uuid.UUID:
    return uuid.UUID(run["id"])


async def test_batch_reconciliation_marks_failed_runs(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    fake_s3: FakeS3,
    submitted: list[NextflowLaunch],
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers, sample = await _setup(client, make_user, make_workspace, login, fake_s3)
    run = (
        await client.post(
            "/api/v1/runs",
            json={"pipelineId": "sarek", "sampleIds": [sample["id"]]},
            headers=headers,
        )
    ).json()

    statuses = iter(["RUNNABLE", "RUNNING", "FAILED"])
    monkeypatch.setattr(
        batch_service,
        "describe_job",
        lambda job_id: {
            "jobId": job_id,
            "status": next(statuses),
            "statusReason": "Essential container in task exited",
        },
    )
    expected = [JobStatus.submitted, JobStatus.running, JobStatus.failed]
    for want in expected:
        assert await run_lifecycle.reconcile_all(session_factory) == 1
        async with session_factory() as session:
            job = await session.get(PipelineJob, launch_id(run))
            assert job is not None and job.status == want
    assert await run_lifecycle.reconcile_all(session_factory) == 0

    logs = (await client.get(f"/api/v1/runs/{run['id']}/logs", headers=headers)).json()
    assert "Essential container in task exited" in logs[-2]["message"]
    # Failed runs leave samples in processing: they need a new run.
    sample_now = await client.get(f"/api/v1/samples/{sample['id']}", headers=headers)
    assert sample_now.json()["status"] == "processing"


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ({"pipelineId": "chipseq"}, "cannot be launched from the LIMS"),
        (
            {"pipelineId": "sarek", "parameters": {"outdir": "s3://elsewhere"}},
            "set by the platform",
        ),
        ({"pipelineId": "sarek", "parameters": {"bad name": "x"}}, "Invalid parameter name"),
        ({"pipelineId": "sarek", "parameters": {"tools": ["a", "b"]}}, "string, number or boolean"),
    ],
)
async def test_launch_rejects_unrunnable_requests(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    fake_s3: FakeS3,
    payload: dict[str, Any],
    detail: str,
) -> None:
    headers, sample = await _setup(client, make_user, make_workspace, login, fake_s3)
    response = await client.post(
        "/api/v1/runs", json={**payload, "sampleIds": [sample["id"]]}, headers=headers
    )
    assert response.status_code == 422
    assert detail in response.json()["detail"]


async def test_launch_requires_verified_reads(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    fake_s3: FakeS3,
) -> None:
    lead = await make_user("lead@lab.io")
    await make_workspace("lab-west", {lead.id: Role.bioinformatics_lead})
    headers = {**(await login("lead@lab.io")), "X-LabChain-Workspace": "lab-west"}
    sample = (
        await client.post(
            "/api/v1/samples",
            json={"sampleCode": "NOREADS", "modality": "genomics"},
            headers=headers,
        )
    ).json()
    await client.post(
        "/api/v1/fastq/register",
        json={"filename": "n_R1.fastq.gz", "sampleId": sample["id"], "readPair": "R1"},
        headers=headers,
    )
    response = await client.post(
        "/api/v1/runs", json={"pipelineId": "rnaseq", "sampleIds": [sample["id"]]}, headers=headers
    )
    assert response.status_code == 422
    assert "No verified R1 FASTQ for sample(s): NOREADS" in response.json()["detail"]


async def test_sse_stream_replays_log_and_ends_on_terminal_status(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    fake_s3: FakeS3,
    submitted: list[NextflowLaunch],
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from app.api.v1.endpoints import runs as runs_endpoint

    monkeypatch.setattr(runs_endpoint, "AsyncSessionLocal", session_factory)
    headers, sample = await _setup(client, make_user, make_workspace, login, fake_s3)
    run = (
        await client.post(
            "/api/v1/runs",
            json={"pipelineId": "sarek", "sampleIds": [sample["id"]]},
            headers=headers,
        )
    ).json()
    async with session_factory() as session:
        job = await session.get(PipelineJob, launch_id(run))
        assert job is not None
        await run_lifecycle.finalize(session, job, success=False, reason="boom")
        await session.commit()

    events = [e async for e in runs_endpoint._log_events("lab-west", launch_id(run))]
    kinds = [e["event"] for e in events]
    assert kinds.count("log") >= 4
    assert ("status", "failed") in [(e["event"], e["data"]) for e in events]
    assert events[-1] == {"event": "end", "data": "failed"}
    assert any("Run failed: boom" in e["data"] for e in events if e["event"] == "log")

    foreign = [e async for e in runs_endpoint._log_events("lab-east", launch_id(run))]
    assert foreign == [{"event": "end", "data": "run-not-found"}]
