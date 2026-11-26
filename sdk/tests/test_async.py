"""
AsyncClient: parity with Client, and the same behaviour through ``httpx.AsyncClient``.

The SDK test suite runs without pytest-asyncio (``-p no:asyncio``), so each test drives its
coroutine with ``asyncio.run``.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

import httpx
import pytest
from fakes import BASE_URL, TOKEN, WORKSPACE, FakeServer, body_of, ok, run_json, sample_json
from test_workflows import READS, STREAM, _serve_fastq, _serve_result

from titerlane import (
    APIConnectionError,
    AsyncClient,
    AuthenticationError,
    ChecksumMismatchError,
    Client,
    ConfigurationError,
    ExecutionDisabledError,
    NotFoundError,
    PermissionDeniedError,
    RunEvent,
    RunFailedError,
    ServerError,
)
from titerlane.models import FastqVerificationStatus, JobStatus

T = TypeVar("T")

RESOURCES = [
    "auth",
    "auth.tokens",
    "workspaces",
    "members",
    "samples",
    "sequencing_runs",
    "fastq",
    "pipelines",
    "runs",
    "results",
]
# Methods returning an iterator: async iterators in AsyncClient, not coroutines.
ITERATORS = {"iter", "stream_logs"}


def _resolve(root: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        root = getattr(root, part)
    return root


def _public_methods(obj: Any) -> dict[str, Callable[..., Any]]:
    return {
        name: getattr(obj, name)
        for name in dir(obj)
        if not name.startswith("_") and callable(getattr(obj, name))
    }


def _parameters(func: Callable[..., Any], *, annotations: bool) -> list[tuple[Any, ...]]:
    return [
        (p.name, p.kind, p.default, p.annotation if annotations else None)
        for p in inspect.signature(func).parameters.values()
        if p.name not in {"self", "cls", "_http", "transport"}
    ]


@pytest.fixture
def sync_and_async() -> tuple[Client, AsyncClient]:
    def refuse(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    return (
        Client(BASE_URL, token="x", transport=httpx.MockTransport(refuse)),
        AsyncClient(BASE_URL, token="x", transport=httpx.MockTransport(refuse)),
    )


@pytest.mark.parametrize("resource", RESOURCES)
def test_resources_mirror_the_sync_client(
    resource: str, sync_and_async: tuple[Client, AsyncClient]
) -> None:
    sync_client, async_client = sync_and_async
    sync_methods = _public_methods(_resolve(sync_client, resource))
    async_methods = _public_methods(_resolve(async_client, resource))

    assert set(async_methods) == set(sync_methods), resource
    for name, sync_method in sync_methods.items():
        async_method = async_methods[name]
        assert _parameters(async_method, annotations=True) == _parameters(
            sync_method, annotations=True
        ), f"{resource}.{name} signature differs"
        if name in ITERATORS:
            assert not inspect.iscoroutinefunction(async_method), f"{resource}.{name}"
        else:
            assert inspect.iscoroutinefunction(async_method), f"{resource}.{name} is not async"
    sync_client.close()


@pytest.mark.parametrize("name", ["login", "with_workspace", "health", "close"])
def test_client_methods_mirror_the_sync_client(name: str) -> None:
    sync_params = _parameters(getattr(Client, name), annotations=False)
    assert _parameters(getattr(AsyncClient, name), annotations=False) == sync_params


# --- Behaviour -----------------------------------------------------------------------------


@pytest.fixture
def aclient(server: FakeServer) -> AsyncClient:
    return AsyncClient(
        BASE_URL, token=TOKEN, workspace=WORKSPACE, transport=httpx.MockTransport(server)
    )


@pytest.fixture(autouse=True)
def no_async_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("asyncio.sleep", sleep)
    return delays


def run(client: AsyncClient, use: Callable[[AsyncClient], Awaitable[T]]) -> T:
    async def main() -> T:
        async with client:
            return await use(client)

    return asyncio.run(main())


async def _collect(iterator: Any) -> list[Any]:
    return [item async for item in iterator]


def test_sends_auth_workspace_and_user_agent(aclient: AsyncClient, server: FakeServer) -> None:
    server.on("GET", "/api/v1/samples", ok([sample_json()]))
    [sample] = run(aclient, lambda c: c.samples.list())

    assert sample.sample_code == "S-001"
    request = server.last("GET", "/api/v1/samples")
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.headers["X-Titerlane-Workspace"] == WORKSPACE
    assert request.headers["User-Agent"].startswith("titerlane-biologics-sdk/")


def test_with_workspace_and_missing_workspace(server: FakeServer) -> None:
    server.on("GET", "/api/v1/samples", ok([]))
    client = AsyncClient(BASE_URL, token=TOKEN, transport=httpx.MockTransport(server))

    async def use(c: AsyncClient) -> None:
        with pytest.raises(ConfigurationError, match="with_workspace"):
            await c.samples.list()
        await c.with_workspace("lab-east").samples.list()

    run(client, use)
    assert len(server.requests) == 1
    assert server.requests[0].headers["X-Titerlane-Workspace"] == "lab-east"


def test_reads_configuration_from_environment(
    server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TITERLANE_URL", BASE_URL)
    monkeypatch.setenv("TITERLANE_TOKEN", "lcb_pat_from_env")
    monkeypatch.setenv("TITERLANE_WORKSPACE", "lab-env")
    server.on("GET", "/api/v1/samples", ok([]))
    run(AsyncClient(transport=httpx.MockTransport(server)), lambda c: c.samples.list())
    request = server.last("GET", "/api/v1/samples")
    assert request.headers["Authorization"] == "Bearer lcb_pat_from_env"
    assert request.headers["X-Titerlane-Workspace"] == "lab-env"


def test_login_then_uses_the_session_token(server: FakeServer) -> None:
    server.on("POST", "/api/v1/auth/login", ok({"accessToken": "jwt", "expiresIn": 3600}))
    server.on("GET", "/api/v1/workspaces", ok([]))

    async def main() -> None:
        client = await AsyncClient.login(
            "a@lab.test", "pw", base_url=BASE_URL, transport=httpx.MockTransport(server)
        )
        async with client:
            await client.workspaces.list()

    asyncio.run(main())
    assert body_of(server.last("POST", "/api/v1/auth/login")) == {
        "email": "a@lab.test",
        "password": "pw",
    }
    assert server.last("GET", "/api/v1/workspaces").headers["Authorization"] == "Bearer jwt"


def test_errors_are_mapped_and_never_show_the_token(
    aclient: AsyncClient, server: FakeServer
) -> None:
    server.on("GET", "/api/v1/auth/me", ok({"detail": "Could not validate credentials"}, 401))
    server.on("POST", "/api/v1/runs", ok({"detail": "Requires bioinformatics_lead"}, 403))

    async def use(c: AsyncClient) -> None:
        with pytest.raises(AuthenticationError) as exc_info:
            await c.auth.me()
        assert TOKEN not in str(exc_info.value)
        with pytest.raises(PermissionDeniedError, match="bioinformatics_lead"):
            await c.runs.launch("rnaseq")

    run(aclient, use)
    assert TOKEN not in repr(aclient)


def test_get_is_retried_but_post_is_not(
    aclient: AsyncClient, server: FakeServer, no_async_sleep: list[float]
) -> None:
    server.on("GET", "/api/v1/samples", ok({}, 503), ok({}, 502), ok([sample_json()]))
    server.on("POST", "/api/v1/samples", ok({"detail": "busy"}, 503))

    async def use(c: AsyncClient) -> None:
        assert len(await c.samples.list()) == 1
        with pytest.raises(ServerError):
            await c.samples.create(sample_code="S", modality="genomics")

    run(aclient, use)
    assert [r.method for r in server.requests] == ["GET", "GET", "GET", "POST"]
    assert no_async_sleep == [0.5, 1.0]


def test_network_failure_raises_connection_error() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = AsyncClient(BASE_URL, token=TOKEN, transport=httpx.MockTransport(fail))
    with pytest.raises(APIConnectionError, match="ConnectError"):
        run(client, lambda c: c.health())


def test_iter_walks_all_pages(aclient: AsyncClient, server: FakeServer) -> None:
    server.on(
        "GET",
        "/api/v1/samples",
        ok([sample_json(sampleCode="A"), sample_json(sampleCode="B")]),
        ok([sample_json(sampleCode="C")]),
    )
    samples = run(aclient, lambda c: _collect(c.samples.iter(status="registered", page_size=2)))

    assert [s.sample_code for s in samples] == ["A", "B", "C"]
    offsets = [r.url.params["offset"] for r in server.requests]
    assert offsets == ["0", "2"]
    assert server.requests[0].url.params["status"] == "registered"


def test_import_csv_uploads_multipart(
    aclient: AsyncClient, server: FakeServer, tmp_path: Path
) -> None:
    csv_path = tmp_path / "samples.csv"
    csv_path.write_text("sampleCode,modality\nS-1,genomics\n", encoding="utf-8")
    result_body = {"created": 1, "skipped": 0, "errors": [], "samples": [sample_json()]}
    server.on("POST", "/api/v1/samples/import", ok(result_body))

    result = run(aclient, lambda c: c.samples.import_csv(csv_path))

    assert result.created == 1
    request = server.last("POST", "/api/v1/samples/import")
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    assert b"S-1,genomics" in request.content


@pytest.fixture
def reads(tmp_path: Path) -> Path:
    path = tmp_path / "reads.fastq.gz"
    path.write_bytes(READS)
    return path


def test_upload_registers_puts_and_verifies(
    aclient: AsyncClient, server: FakeServer, reads: Path
) -> None:
    fastq_id = _serve_fastq(server, "verified")

    fastq = run(aclient, lambda c: c.fastq.upload(reads, read_pair="R1"))

    assert str(fastq.id) == fastq_id
    assert fastq.verification_status is FastqVerificationStatus.verified
    put = server.last("PUT", "/bucket/lab-west/fastq/reads.fastq.gz")
    assert put.content == READS
    assert put.headers["Content-Type"] == "application/gzip"
    assert put.headers["Content-Length"] == str(len(READS))
    assert "Authorization" not in put.headers
    assert "X-Titerlane-Workspace" not in put.headers
    assert [r.method for r in server.requests] == ["POST", "PUT", "POST", "GET"]


def test_upload_mismatch_and_manifest_check(
    aclient: AsyncClient, server: FakeServer, reads: Path
) -> None:
    _serve_fastq(server, "mismatch")

    async def use(c: AsyncClient) -> None:
        with pytest.raises(ChecksumMismatchError, match="nothing was uploaded"):
            await c.fastq.upload(reads, expected_md5="f" * 32)
        assert server.requests == []
        with pytest.raises(ChecksumMismatchError, match="mismatch"):
            await c.fastq.upload(reads)

    run(aclient, use)


def test_download_checks_md5(aclient: AsyncClient, server: FakeServer, tmp_path: Path) -> None:
    content = b"##fileformat=VCFv4.2\n"
    good = _serve_result(server, content, hashlib.md5(content).hexdigest())

    path = run(aclient, lambda c: c.results.download(good, tmp_path))

    assert path == tmp_path / "variants.vcf.gz"
    assert path.read_bytes() == content
    assert "Authorization" not in server.last("GET", "/bucket/out/variants.vcf.gz").headers


def test_download_mismatch_leaves_nothing_behind(
    aclient: AsyncClient, server: FakeServer, tmp_path: Path
) -> None:
    bad = _serve_result(server, b"corrupted", "0" * 32)
    with pytest.raises(ChecksumMismatchError):
        run(aclient, lambda c: c.results.download(bad, tmp_path / "variants.vcf.gz"))
    assert list(tmp_path.iterdir()) == []


def test_wait_polls_until_success(
    aclient: AsyncClient, server: FakeServer, no_async_sleep: list[float]
) -> None:
    run_id = str(uuid.uuid4())
    server.on(
        "GET",
        f"/api/v1/runs/{run_id}",
        ok(run_json(id=run_id, status="running")),
        ok(run_json(id=run_id, status="succeeded")),
    )
    result = run(aclient, lambda c: c.runs.wait(run_id, poll_interval=5))
    assert result.status is JobStatus.succeeded
    assert no_async_sleep == [5]


def test_wait_refuses_disabled_execution_and_reports_failure(
    aclient: AsyncClient, server: FakeServer
) -> None:
    pending, failed = str(uuid.uuid4()), str(uuid.uuid4())
    server.on(
        "GET",
        f"/api/v1/runs/{pending}",
        ok(run_json(id=pending, status="pending", executionSubmitted=False)),
    )
    server.on(
        "GET",
        f"/api/v1/runs/{failed}",
        ok(run_json(id=failed, status="failed", progress={"errorMessage": "OOM"})),
    )

    async def use(c: AsyncClient) -> None:
        with pytest.raises(ExecutionDisabledError):
            await c.runs.wait(pending)
        with pytest.raises(RunFailedError, match="OOM"):
            await c.runs.wait(failed)

    run(aclient, use)


def test_stream_logs_yields_events_until_end(aclient: AsyncClient, server: FakeServer) -> None:
    run_id = str(uuid.uuid4())
    server.on(
        "GET",
        f"/api/v1/runs/{run_id}/logs/stream",
        httpx.Response(200, text=STREAM, headers={"Content-Type": "text/event-stream"}),
    )
    events = run(aclient, lambda c: _collect(c.runs.stream_logs(run_id)))

    assert events == [
        RunEvent("log", "2026-11-25T12:00:00Z Samplesheet written", 0),
        RunEvent("status", "running"),
        RunEvent("log", "line one\nline two", 1),
        RunEvent("end", "succeeded"),
    ]


def test_stream_logs_maps_errors(aclient: AsyncClient, server: FakeServer) -> None:
    run_id = str(uuid.uuid4())
    server.on("GET", f"/api/v1/runs/{run_id}/logs/stream", ok({"detail": "Run not found"}, 404))
    with pytest.raises(NotFoundError, match="Run not found"):
        run(aclient, lambda c: _collect(c.runs.stream_logs(run_id)))
