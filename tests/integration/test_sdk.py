"""
The Python SDK (``sdk/``) against the real application over real HTTP.

The app runs in a uvicorn thread on the integration database. Signed storage URLs from the
``fake_s3`` fixture (``upload.test`` / ``download.test``) are served by the in-memory store;
everything else goes over the network to the local server. Skipped when the SDK is not
installed (``uv sync --all-packages``).
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1.endpoints import runs as runs_endpoint
from app.core.config import settings
from app.main import app
from app.models.user import Role, User
from app.models.workspace import Workspace
from app.services.batch import BatchSubmissionResult, NextflowLaunch, batch_service
from tests.integration.conftest import PASSWORD, FakeS3

labchain = pytest.importorskip("labchain")

from labchain import (  # noqa: E402
    AuthenticationError,
    Client,
    ConflictError,
    ExecutionDisabledError,
    NotFoundError,
    PermissionDeniedError,
)
from labchain.models import FastqVerificationStatus, JobStatus  # noqa: E402

MakeUser = Callable[..., Awaitable[User]]
MakeWorkspace = Callable[..., Awaitable[Workspace]]


class StorageRouter(httpx.BaseTransport):
    """Serves the fake signed storage URLs in memory; sends API calls over the network."""

    def __init__(self, store: FakeS3) -> None:
        self.store = store
        self.network = httpx.HTTPTransport()
        self.storage_requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        key = request.url.path.lstrip("/")
        if request.url.host == "upload.test" and request.method == "PUT":
            self.storage_requests.append(request)
            self.store.objects[key] = request.read()
            return httpx.Response(200)
        if request.url.host == "download.test" and request.method == "GET":
            self.storage_requests.append(request)
            data = self.store.objects.get(key)
            return httpx.Response(200, content=data) if data is not None else httpx.Response(404)
        return self.network.handle_request(request)

    def close(self) -> None:
        self.network.close()


@pytest.fixture
async def base_url(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[str]:
    """
    The app over real HTTP. Depends on ``client`` so the test database override is active;
    the SSE log stream opens its own sessions, so it is pointed at the test database too.
    Lifespan is off: it would reach object storage and start the AWS Batch monitor.
    """
    monkeypatch.setattr(runs_endpoint, "AsyncSessionLocal", session_factory)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, lifespan="off", log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def router(fake_s3: FakeS3) -> Iterator[StorageRouter]:
    transport = StorageRouter(fake_s3)
    yield transport
    transport.close()


@pytest.fixture
def submitted(monkeypatch: pytest.MonkeyPatch) -> list[NextflowLaunch]:
    """AWS Batch enabled: capture launches instead of calling AWS."""
    launches: list[NextflowLaunch] = []

    def submit(launch: NextflowLaunch, *, workspace: str) -> BatchSubmissionResult:
        launches.append(launch)
        return BatchSubmissionResult(job_id="batch-job-1", submitted=True)

    monkeypatch.setattr(batch_service, "submit", submit)
    return launches


def _token_client(base_url: str, router: StorageRouter, email: str, workspace: str) -> Client:
    """Sign in with the password once, then work with a personal access token."""
    with Client.login(email, PASSWORD, base_url=base_url, transport=router) as session:
        token = session.auth.tokens.create("sdk integration").token
    return Client(base_url, token=token, workspace=workspace, transport=router)


def _fastq(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(f"@{name}\nACGT\n+\nIIII\n".encode() * 50)
    return path


async def test_sample_to_results_workflow(
    base_url: str,
    router: StorageRouter,
    make_user: MakeUser,
    fake_s3: FakeS3,
    submitted: list[NextflowLaunch],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "public_api_url", "https://api.test")
    await make_user("lead@lab.io")
    with Client.login("lead@lab.io", PASSWORD, base_url=base_url, transport=router) as session:
        workspace = session.workspaces.create("lab-west", "Lab West")
        assert workspace.role == "bioinformatics_lead"
        token = session.auth.tokens.create("pipeline bot", expires_in_days=7)

    with Client(base_url, token=token.token, workspace="lab-west", transport=router) as client:
        assert client.auth.me().memberships[0].slug == "lab-west"
        sample = client.samples.create(
            sample_code="SMP-001",
            modality="genomics",
            assay="exome",
            sample_type="tumor",
            patient_id="PT-1",
        )
        run_record = client.sequencing_runs.create(run_name="NovaSeq-01")
        uploaded = [
            client.fastq.upload(
                _fastq(tmp_path, f"smp_{pair}.fastq.gz"),
                sample_id=sample.id,
                sequencing_run_id=run_record.id,
                read_pair=pair,
            )
            for pair in ("R1", "R2")
        ]
        assert all(f.verification_status is FastqVerificationStatus.verified for f in uploaded)
        assert client.samples.get(sample.id).status.value == "fastq_received"
        assert {f.id for f in client.fastq.iter(sample_id=sample.id)} == {f.id for f in uploaded}
        # Signed URLs never receive the API credentials.
        assert router.storage_requests
        assert all("Authorization" not in r.headers for r in router.storage_requests)

        run = client.runs.launch(
            "sarek", sample_ids=[sample.id], parameters={"tools": "mutect2", "skip_qc": True}
        )
        assert run.execution_submitted and run.status is JobStatus.submitted

        # Nextflow reports progress, writes outputs, then completes.
        events_path = submitted[0].weblog_url.removeprefix("https://api.test")  # type: ignore[union-attr]  # set because public_api_url is
        prefix = f"lab-west/results/{run.id}/"
        fake_s3.objects[prefix + "multiqc/multiqc_report.html"] = b"<html>report</html>"
        fake_s3.objects[prefix + "variant_calling/mutect2/smp.vcf.gz"] = b"##fileformat=VCFv4.2"
        with httpx.Client(base_url=base_url) as nextflow:
            for event in (
                {"event": "started", "utcTime": "2026-11-25T10:00:00Z"},
                {"event": "completed", "metadata": {"workflow": {"success": True}}},
            ):
                assert nextflow.post(events_path, json=event).status_code == 204

        done = client.runs.wait(run.id, timeout=30, poll_interval=0.1)
        assert done.status is JobStatus.succeeded
        events = list(client.runs.stream_logs(run.id))
        assert events[-1].kind == "end" and events[-1].data == "succeeded"
        assert [line.index for line in client.runs.logs(run.id)][:2] == [0, 1]

        outputs = {o.filename: o for o in client.results.for_run(run.id)}
        assert set(outputs) == {"multiqc_report.html", "smp.vcf.gz"}
        vcf = client.results.download(outputs["smp.vcf.gz"].id, tmp_path)
        assert vcf.read_bytes() == b"##fileformat=VCFv4.2"
        assert client.results.list(run_id=run.id, file_type="vcf")[0].filename == "smp.vcf.gz"

        updated = client.samples.bulk_update({sample.id: {"qc_status": "pass"}})
        assert updated[0].qc_status.value == "pass"
        client.samples.delete(sample.id)
        with pytest.raises(NotFoundError):
            client.samples.get(sample.id)
        with pytest.raises(ConflictError, match="deleted sample"):
            client.samples.create(sample_code="SMP-001", modality="genomics")


async def test_csv_import_and_pagination(
    base_url: str,
    router: StorageRouter,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    tmp_path: Path,
) -> None:
    tech = await make_user("tech@lab.io")
    await make_workspace("lab-west", {tech.id: Role.lab_technician})
    csv_path = tmp_path / "samples.csv"
    rows = "".join(f"S-{i:03d},transcriptomics\n" for i in range(7))
    csv_path.write_text("sampleCode,modality\n" + rows + "S-000,genomics\n", encoding="utf-8")

    with _token_client(base_url, router, "tech@lab.io", "lab-west") as client:
        result = client.samples.import_csv(csv_path)
        assert (result.created, result.skipped) == (7, 1)
        codes = [s.sample_code for s in client.samples.iter(page_size=3)]
        assert sorted(codes) == [f"S-{i:03d}" for i in range(7)]
        assert client.samples.bulk_delete([s.id for s in result.samples[:2]]) == 2
        assert len(list(client.samples.iter(modality="transcriptomics"))) == 5


async def test_permissions_isolation_and_revocation(
    base_url: str, router: StorageRouter, make_user: MakeUser, make_workspace: MakeWorkspace
) -> None:
    tech = await make_user("tech@lab.io")
    bob = await make_user("bob@lab.io")
    await make_workspace("lab-west", {tech.id: Role.lab_technician})
    await make_workspace("lab-east", {bob.id: Role.bioinformatics_lead})

    with _token_client(base_url, router, "bob@lab.io", "lab-east") as bob_client:
        foreign_sample = bob_client.samples.create(sample_code="E-1", modality="genomics")

    with _token_client(base_url, router, "tech@lab.io", "lab-west") as client:
        with pytest.raises(PermissionDeniedError):
            client.runs.launch("rnaseq")
        with pytest.raises(PermissionDeniedError):
            client.members.add("bob@lab.io")
        with pytest.raises(NotFoundError, match="lab-east"):
            client.with_workspace("lab-east").samples.list()
        with pytest.raises(NotFoundError):
            client.samples.get(foreign_sample.id)
        with pytest.raises(PermissionDeniedError):
            client.auth.tokens.create("escalate")

        [own] = client.auth.tokens.list()
        client.auth.tokens.revoke(own.id)
        with pytest.raises(AuthenticationError):
            client.auth.me()


async def test_wait_refuses_runs_that_will_never_execute(
    base_url: str,
    router: StorageRouter,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    tmp_path: Path,
) -> None:
    lead = await make_user("lead@lab.io")
    await make_workspace("lab-west", {lead.id: Role.bioinformatics_lead})

    with _token_client(base_url, router, "lead@lab.io", "lab-west") as client:
        sample = client.samples.create(
            sample_code="RNA-1", modality="transcriptomics", assay="bulk_rna"
        )
        for pair in ("R1", "R2"):
            client.fastq.upload(
                _fastq(tmp_path, f"rna_{pair}.fastq.gz"), sample_id=sample.id, read_pair=pair
            )
        run = client.runs.launch("rnaseq", sample_ids=[sample.id])

        assert run.execution_submitted is False and run.status is JobStatus.pending
        with pytest.raises(ExecutionDisabledError):
            client.runs.wait(run.id, timeout=5, poll_interval=0.1)
        events = list(client.runs.stream_logs(run.id))
        assert events[-1].kind == "end" and events[-1].data == "pending"
        assert any("Not submitted" in e.data for e in events if e.kind == "log")


async def test_fastq_mismatch_is_reported(
    base_url: str,
    router: StorageRouter,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    fake_s3: FakeS3,
    tmp_path: Path,
) -> None:
    tech = await make_user("tech@lab.io")
    await make_workspace("lab-west", {tech.id: Role.lab_technician})
    reads = _fastq(tmp_path, "reads.fastq.gz")

    with _token_client(base_url, router, "tech@lab.io", "lab-west") as client:
        registration = client.fastq.register(
            filename=reads.name, expected_md5=hashlib.md5(b"something else").hexdigest()
        )
        fake_s3.objects[registration.s3_key] = reads.read_bytes()
        verification = client.fastq.verify(registration.id)
        assert verification.verification_status is FastqVerificationStatus.mismatch
