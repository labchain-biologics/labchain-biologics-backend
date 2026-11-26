"""Run execution: samplesheet, submission, Nextflow weblog lifecycle, Batch reconciliation."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.audit import AuditLog
from app.models.pipeline import JobStatus, PipelineJob
from app.models.user import Role, User
from app.models.workspace import Workspace, WorkspaceMembership
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
    headers = {**(await login("lead@lab.io")), "X-Titerlane-Workspace": "lab-west"}
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
    headers = {**(await login("lead@lab.io")), "X-Titerlane-Workspace": "lab-west"}
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

    async with session_factory() as session:
        lead_id = await session.scalar(select(User.id).where(User.email == "lead@lab.io"))
    assert lead_id is not None
    events = [e async for e in runs_endpoint._log_events("lab-west", launch_id(run), lead_id)]
    kinds = [e["event"] for e in events]
    assert kinds.count("log") >= 4
    assert ("status", "failed") in [(e["event"], e["data"]) for e in events]
    assert events[-1] == {"event": "end", "data": "failed"}
    assert any("Run failed: boom" in e["data"] for e in events if e["event"] == "log")

    # Not a member of lab-east: the stream closes before reading anything.
    foreign = [e async for e in runs_endpoint._log_events("lab-east", launch_id(run), lead_id)]
    assert foreign == [{"event": "end", "data": "access-revoked"}]

    # Membership removed while subscribed: the next poll ends the stream.
    async with session_factory() as session:
        await session.execute(
            delete(WorkspaceMembership).where(WorkspaceMembership.user_id == lead_id)
        )
        await session.commit()
    revoked = [e async for e in runs_endpoint._log_events("lab-west", launch_id(run), lead_id)]
    assert revoked == [{"event": "end", "data": "access-revoked"}]


async def _register(
    client: httpx.AsyncClient,
    headers: Headers,
    fake_s3: FakeS3,
    sample_id: str,
    pair: str,
    *,
    run_id: str | None = None,
    content: bytes | None = None,
) -> dict[str, Any]:
    registered = (
        await client.post(
            "/api/v1/fastq/register",
            json={
                "filename": f"x_{pair}.fastq.gz",
                "sampleId": sample_id,
                "readPair": pair,
                "sequencingRunId": run_id,
            },
            headers=headers,
        )
    ).json()
    fake_s3.objects[registered["s3Key"]] = content or f"reads {pair} {run_id}".encode()
    verified = await client.post(f"/api/v1/fastq/{registered['id']}/verify", headers=headers)
    assert verified.json()["verificationStatus"] == "verified"
    return registered


async def _lead_headers(
    make_user: MakeUser, make_workspace: MakeWorkspace, login: Login
) -> Headers:
    lead = await make_user("lead@lab.io")
    await make_workspace("lab-west", {lead.id: Role.bioinformatics_lead})
    return {**(await login("lead@lab.io")), "X-Titerlane-Workspace": "lab-west"}


async def test_launch_refuses_inputs_replaced_after_verification(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    fake_s3: FakeS3,
) -> None:
    headers, sample = await _setup(client, make_user, make_workspace, login, fake_s3)
    listed = (await client.get(f"/api/v1/fastq?sampleId={sample['id']}", headers=headers)).json()
    r1 = next(f for f in listed if f["readPair"] == "R1")
    fake_s3.objects[r1["s3Key"]] = b"swapped content"

    response = await client.post(
        "/api/v1/runs", json={"pipelineId": "sarek", "sampleIds": [sample["id"]]}, headers=headers
    )
    assert response.status_code == 422
    assert "changed or missing since verification" in response.json()["detail"]


async def test_fastq_keys_are_unique_and_confined_to_the_workspace(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    fake_s3: FakeS3,
) -> None:
    headers = await _lead_headers(make_user, make_workspace, login)
    body = {"filename": "same.fastq.gz"}
    first = (await client.post("/api/v1/fastq/register", json=body, headers=headers)).json()
    second = (await client.post("/api/v1/fastq/register", json=body, headers=headers)).json()
    assert first["s3Key"] != second["s3Key"]
    assert first["s3Key"].startswith("lab-west/fastq/")

    foreign = await client.post(
        "/api/v1/fastq/register",
        json={"filename": "x.fastq.gz", "s3Key": "lab-east/fastq/their.fastq.gz"},
        headers=headers,
    )
    assert foreign.status_code == 422


async def test_paired_pipelines_need_r2_from_the_same_run(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    fake_s3: FakeS3,
) -> None:
    headers = await _lead_headers(make_user, make_workspace, login)
    sample = (
        await client.post(
            "/api/v1/samples",
            json={"sampleCode": "SC1", "modality": "transcriptomics"},
            headers=headers,
        )
    ).json()
    runs = []
    for name in ("old", "new"):
        created = await client.post(
            "/api/v1/sequencing-runs", json={"runName": name}, headers=headers
        )
        runs.append(created.json()["id"])
    await _register(client, headers, fake_s3, sample["id"], "R2", run_id=runs[0])
    await _register(client, headers, fake_s3, sample["id"], "R1", run_id=runs[1])

    paired = await client.post(
        "/api/v1/runs",
        json={"pipelineId": "scrnaseq", "sampleIds": [sample["id"]]},
        headers=headers,
    )
    assert paired.status_code == 422
    assert "needs paired reads" in paired.json()["detail"]

    # rnaseq accepts single-end reads: the R2 of the other run is not paired with this R1.
    single = await client.post(
        "/api/v1/runs",
        json={"pipelineId": "rnaseq", "sampleIds": [sample["id"]]},
        headers=headers,
    )
    assert single.status_code == 201, single.text
    sheet_key = f"lab-west/runs/{single.json()['id']}/samplesheet.csv"
    row = fake_s3.objects[sheet_key].decode().splitlines()[1].split(",")
    assert row[2] == ""


async def test_samplesheet_rejects_colliding_sample_identifiers(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    fake_s3: FakeS3,
) -> None:
    headers = await _lead_headers(make_user, make_workspace, login)
    ids = []
    for code in ("RNA 1", "RNA_1"):
        sample = (
            await client.post(
                "/api/v1/samples",
                json={"sampleCode": code, "modality": "transcriptomics"},
                headers=headers,
            )
        ).json()
        await _register(client, headers, fake_s3, sample["id"], "R1", content=code.encode())
        ids.append(sample["id"])
    response = await client.post(
        "/api/v1/runs", json={"pipelineId": "rnaseq", "sampleIds": ids}, headers=headers
    )
    assert response.status_code == 422
    assert "both become 'RNA_1'" in response.json()["detail"]


async def test_failed_output_collection_is_retried_and_late_events_ignored(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    fake_s3: FakeS3,
    submitted: list[NextflowLaunch],
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_lifecycle.settings, "public_api_url", "https://api.test")
    headers, sample = await _setup(client, make_user, make_workspace, login, fake_s3)
    run = (
        await client.post(
            "/api/v1/runs",
            json={"pipelineId": "sarek", "sampleIds": [sample["id"]]},
            headers=headers,
        )
    ).json()
    weblog_url = submitted[0].weblog_url
    assert weblog_url is not None
    events_url = weblog_url.removeprefix("https://api.test")
    fake_s3.objects[f"lab-west/results/{run['id']}/multiqc/multiqc_report.html"] = b"<html/>"

    fake_s3.fail_listing = True
    done = {"event": "completed", "metadata": {"workflow": {"success": True}}}
    assert (await client.post(events_url, json=done)).status_code == 204
    failed = (await client.get(f"/api/v1/runs/{run['id']}", headers=headers)).json()
    assert failed["status"] == "succeeded"
    assert failed["progress"]["outputs"] == "pending"
    assert failed["outputFiles"] == []

    # A late process event changes nothing on the finished run.
    late = {"event": "process_completed", "trace": {"name": "LATE", "status": "COMPLETED"}}
    assert (await client.post(events_url, json=late)).status_code == 204

    fake_s3.fail_listing = False
    await run_lifecycle.reconcile_all(session_factory)
    collected = (await client.get(f"/api/v1/runs/{run['id']}", headers=headers)).json()
    assert collected["progress"]["outputs"] == "collected"
    assert "processesCompleted" not in collected["progress"]
    assert [f["filename"] for f in collected["outputFiles"]] == ["multiqc_report.html"]

    async with session_factory() as session:
        audited = await session.scalar(
            select(AuditLog.after_state).where(AuditLog.action == "register_output")
        )
    assert audited is not None and audited["s3Key"].endswith("multiqc_report.html")
