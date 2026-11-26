"""
Asynchronous API resources, exposed as attributes of :class:`titerlane.AsyncClient`.

Each class mirrors its synchronous counterpart method for method (same names, arguments and
return types, awaited); ``sdk/tests/test_async.py`` enforces it. Request bodies and checks are
shared with the synchronous resources so both clients behave identically. File hashing and
disk reads/writes run in a worker thread so they never block the event loop.
"""

from __future__ import annotations

import asyncio
import builtins
import hashlib
import os
import tempfile
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, TypeVar

from titerlane._http import AsyncTransport
from titerlane.models import (
    ApiToken,
    ApiTokenCreate,
    ApiTokenCreated,
    FastqFile,
    FastqRegisterRequest,
    FastqRegistration,
    FastqVerification,
    JobStatus,
    Member,
    MemberCreate,
    MemberUpdate,
    OmicsModality,
    OutputFileType,
    Pipeline,
    QcStatus,
    ResultDownload,
    ResultFile,
    Role,
    Run,
    RunLogLine,
    Sample,
    SampleAssay,
    SampleCreate,
    SampleImportResult,
    SampleStatus,
    SampleUpdate,
    SequencingRun,
    SequencingRunCreate,
    User,
    Workspace,
    WorkspaceCreate,
)
from titerlane.resources._base import CHUNK_SIZE, build, file_md5, parse, parse_list
from titerlane.resources.results import check_download, download_target
from titerlane.resources.runs import (
    MAX_PAGE_SIZE,
    RunEvent,
    SSEDecoder,
    check_deadline,
    finished,
    run_create_body,
)
from titerlane.resources.samples import bulk_patch_body
from titerlane.resources.sequencing import check_manifest, check_verification, upload_headers

T = TypeVar("T")


class AsyncResource:
    def __init__(self, http: AsyncTransport) -> None:
        self._http = http


async def apaginate(
    fetch: Callable[[int, int], Awaitable[list[T]]], page_size: int
) -> AsyncIterator[T]:
    """Walk a limit/offset listing until a short page."""
    offset = 0
    while True:
        page = await fetch(page_size, offset)
        for item in page:
            yield item
        if len(page) < page_size:
            return
        offset += page_size


# --- Auth and workspaces -------------------------------------------------------------------


class AsyncTokens(AsyncResource):
    """Personal access tokens of the current user."""

    async def list(self) -> builtins.list[ApiToken]:
        """Your tokens, newest first, including revoked and expired ones (never the secret)."""
        data = await self._http.request("GET", "/auth/tokens", tenant=False)
        return parse_list(ApiToken, data)

    async def create(self, name: str, *, expires_in_days: int | None = None) -> ApiTokenCreated:
        """
        Issue a token. Its secret (``.token``) is returned only now: store it safely.
        Requires a login session; a personal access token cannot create another one.
        """
        body = ApiTokenCreate(name=name, expires_in_days=expires_in_days).to_json()
        data = await self._http.request("POST", "/auth/tokens", tenant=False, json=body)
        return parse(ApiTokenCreated, data)

    async def revoke(self, token_id: uuid.UUID | str) -> ApiToken:
        """Revoke a token. It stops working immediately."""
        data = await self._http.request("DELETE", f"/auth/tokens/{token_id}", tenant=False)
        return parse(ApiToken, data)


class AsyncAuth(AsyncResource):
    """The current user and their tokens."""

    @property
    def tokens(self) -> AsyncTokens:
        return AsyncTokens(self._http)

    async def me(self) -> User:
        """The current user and their workspaces, with their role in each."""
        return parse(User, await self._http.request("GET", "/auth/me", tenant=False))

    async def logout(self) -> None:
        """Record a logout in the audit trail. The credential itself is not invalidated."""
        await self._http.request("POST", "/auth/logout", tenant=False)


class AsyncWorkspaces(AsyncResource):
    async def list(self) -> builtins.list[Workspace]:
        """Workspaces you belong to, with your role in each."""
        data = await self._http.request("GET", "/workspaces", tenant=False)
        return parse_list(Workspace, data)

    async def create(self, slug: str, name: str) -> Workspace:
        """Create a workspace. You become its ``bioinformatics_lead``."""
        body = WorkspaceCreate(slug=slug, name=name).to_json()
        data = await self._http.request("POST", "/workspaces", tenant=False, json=body)
        return parse(Workspace, data)


class AsyncMembers(AsyncResource):
    """Members of the client's workspace. Changes require the ``bioinformatics_lead`` role."""

    async def list(self) -> builtins.list[Member]:
        return parse_list(Member, await self._http.request("GET", "/members"))

    async def add(self, email: str, role: Role | str = Role.lab_technician) -> Member:
        body = MemberCreate(email=email, role=Role(role)).to_json()
        return parse(Member, await self._http.request("POST", "/members", json=body))

    async def change_role(self, user_id: uuid.UUID | str, role: Role | str) -> Member:
        body = MemberUpdate(role=Role(role)).to_json()
        return parse(Member, await self._http.request("PATCH", f"/members/{user_id}", json=body))

    async def remove(self, user_id: uuid.UUID | str) -> None:
        await self._http.request("DELETE", f"/members/{user_id}")


# --- Samples -------------------------------------------------------------------------------


class AsyncSamples(AsyncResource):
    async def list(
        self,
        *,
        modality: OmicsModality | str | None = None,
        assay: SampleAssay | str | None = None,
        status: SampleStatus | str | None = None,
        qc_status: QcStatus | str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> builtins.list[Sample]:
        """One page of samples, newest first. Use :meth:`iter` to walk all of them."""
        params = {
            "modality": modality,
            "assay": assay,
            "status": status,
            "qcStatus": qc_status,
            "limit": limit,
            "offset": offset,
        }
        return parse_list(Sample, await self._http.request("GET", "/samples", params=params))

    def iter(
        self,
        *,
        modality: OmicsModality | str | None = None,
        assay: SampleAssay | str | None = None,
        status: SampleStatus | str | None = None,
        qc_status: QcStatus | str | None = None,
        page_size: int = MAX_PAGE_SIZE,
    ) -> AsyncIterator[Sample]:
        """Every matching sample, fetched page by page: ``async for sample in ...iter()``."""
        return apaginate(
            lambda limit, offset: self.list(
                modality=modality,
                assay=assay,
                status=status,
                qc_status=qc_status,
                limit=limit,
                offset=offset,
            ),
            page_size,
        )

    async def get(self, sample_id: uuid.UUID | str) -> Sample:
        return parse(Sample, await self._http.request("GET", f"/samples/{sample_id}"))

    async def create(self, sample: SampleCreate | None = None, /, **fields: Any) -> Sample:
        """Register a sample: ``await create(sample_code="S-001", modality="genomics")``."""
        body = build(SampleCreate, sample, fields).to_json()
        return parse(Sample, await self._http.request("POST", "/samples", json=body))

    async def update(
        self, sample_id: uuid.UUID | str, patch: SampleUpdate | None = None, /, **fields: Any
    ) -> Sample:
        """Change only the given fields: ``await update(sample_id, qc_status="pass")``."""
        body = build(SampleUpdate, patch, fields).to_json(exclude_unset=True)
        data = await self._http.request("PATCH", f"/samples/{sample_id}", json=body)
        return parse(Sample, data)

    async def delete(self, sample_id: uuid.UUID | str) -> None:
        await self._http.request("DELETE", f"/samples/{sample_id}")

    async def bulk_update(
        self, patches: Mapping[uuid.UUID | str, SampleUpdate | Mapping[str, Any]]
    ) -> builtins.list[Sample]:
        """Update several samples in one request: ``{sample_id: {"qc_status": "pass"}}``."""
        data = await self._http.request("PATCH", "/samples/bulk", json=bulk_patch_body(patches))
        return parse_list(Sample, data)

    async def bulk_delete(self, sample_ids: Iterable[uuid.UUID | str]) -> int:
        """Delete several samples; returns how many were deleted."""
        body = {"ids": [str(sample_id) for sample_id in sample_ids]}
        data = await self._http.request("DELETE", "/samples/bulk", json=body)
        return int(data["deleted"])

    async def import_csv(self, path: str | Path) -> SampleImportResult:
        """
        Import samples from a UTF-8 CSV whose columns are sample fields (``sampleCode`` or
        ``sample_code``...). Existing or duplicated sample codes are skipped and reported.
        """
        csv_path = Path(path)
        content = await asyncio.to_thread(csv_path.read_bytes)
        files = {"file": (csv_path.name, content, "text/csv")}
        data = await self._http.request("POST", "/samples/import", files=files)
        return parse(SampleImportResult, data)


# --- Sequencing runs and FASTQ -------------------------------------------------------------


class AsyncSequencingRuns(AsyncResource):
    async def list(self, *, limit: int = 100, offset: int = 0) -> builtins.list[SequencingRun]:
        params = {"limit": limit, "offset": offset}
        data = await self._http.request("GET", "/sequencing-runs", params=params)
        return parse_list(SequencingRun, data)

    def iter(self, *, page_size: int = MAX_PAGE_SIZE) -> AsyncIterator[SequencingRun]:
        return apaginate(lambda limit, offset: self.list(limit=limit, offset=offset), page_size)

    async def get(self, run_id: uuid.UUID | str) -> SequencingRun:
        data = await self._http.request("GET", f"/sequencing-runs/{run_id}")
        return parse(SequencingRun, data)

    async def create(
        self, run: SequencingRunCreate | None = None, /, **fields: Any
    ) -> SequencingRun:
        """Record a sequencing run: ``await create(run_name="NovaSeq-2026-11-25")``."""
        body = build(SequencingRunCreate, run, fields).to_json()
        data = await self._http.request("POST", "/sequencing-runs", json=body)
        return parse(SequencingRun, data)


async def _read_chunks(path: Path) -> AsyncIterator[bytes]:
    """A file's content in chunks, each read in a worker thread."""
    handle = await asyncio.to_thread(path.open, "rb")
    try:
        while chunk := await asyncio.to_thread(handle.read, CHUNK_SIZE):
            yield chunk
    finally:
        await asyncio.to_thread(handle.close)


class AsyncFastq(AsyncResource):
    async def list(
        self,
        *,
        sample_id: uuid.UUID | str | None = None,
        sequencing_run_id: uuid.UUID | str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> builtins.list[FastqFile]:
        params = {
            "sampleId": sample_id,
            "sequencingRunId": sequencing_run_id,
            "limit": limit,
            "offset": offset,
        }
        return parse_list(FastqFile, await self._http.request("GET", "/fastq", params=params))

    def iter(
        self,
        *,
        sample_id: uuid.UUID | str | None = None,
        sequencing_run_id: uuid.UUID | str | None = None,
        page_size: int = MAX_PAGE_SIZE,
    ) -> AsyncIterator[FastqFile]:
        return apaginate(
            lambda limit, offset: self.list(
                sample_id=sample_id,
                sequencing_run_id=sequencing_run_id,
                limit=limit,
                offset=offset,
            ),
            page_size,
        )

    async def get(self, fastq_id: uuid.UUID | str) -> FastqFile:
        return parse(FastqFile, await self._http.request("GET", f"/fastq/{fastq_id}"))

    async def register(
        self, request: FastqRegisterRequest | None = None, /, **fields: Any
    ) -> FastqRegistration:
        """
        Record a FASTQ file and get a signed ``upload_url``. Most callers want :meth:`upload`,
        which also sends the file and verifies it.
        """
        body = build(FastqRegisterRequest, request, fields).to_json()
        data = await self._http.request("POST", "/fastq/register", json=body)
        return parse(FastqRegistration, data)

    async def verify(self, fastq_id: uuid.UUID | str) -> FastqVerification:
        """Have the server compute the MD5 of the stored object and compare it."""
        data = await self._http.request("POST", f"/fastq/{fastq_id}/verify")
        return parse(FastqVerification, data)

    async def upload(
        self,
        path: str | Path,
        *,
        sample_id: uuid.UUID | str | None = None,
        sequencing_run_id: uuid.UUID | str | None = None,
        read_pair: str | None = None,
        expected_md5: str | None = None,
    ) -> FastqFile:
        """
        Register, upload and verify a gzipped FASTQ file in one call.

        The MD5 is computed locally (or taken from ``expected_md5``, e.g. from the sequencing
        provider's manifest) and the server checks the stored object against it.

        Raises:
            ChecksumMismatchError: the stored object does not match the expected MD5. The
                record stays in the workspace with status ``mismatch``.
        """
        file_path = Path(path)
        local_md5, size = await asyncio.to_thread(file_md5, file_path)
        check_manifest(file_path, local_md5, expected_md5)
        registration = await self.register(
            filename=file_path.name,
            size_bytes=size,
            expected_md5=local_md5,
            sample_id=sample_id,
            sequencing_run_id=sequencing_run_id,
            read_pair=read_pair,
        )
        await self._http.storage_put(
            registration.upload_url, _read_chunks(file_path), upload_headers(size)
        )
        verification = await self.verify(registration.id)
        check_verification(file_path, local_md5, registration, verification)
        return await self.get(registration.id)


# --- Pipelines, runs and results -----------------------------------------------------------


class AsyncPipelines(AsyncResource):
    async def list(self) -> builtins.list[Pipeline]:
        """The nf-core pipelines this server can run, with their allowed versions."""
        return parse_list(Pipeline, await self._http.request("GET", "/pipelines"))

    async def get(self, pipeline_id: str) -> Pipeline:
        return parse(Pipeline, await self._http.request("GET", f"/pipelines/{pipeline_id}"))


class AsyncRuns(AsyncResource):
    async def list(
        self,
        *,
        status: JobStatus | str | None = None,
        sample_id: uuid.UUID | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[Run]:
        params = {"status": status, "sampleId": sample_id, "limit": limit, "offset": offset}
        return parse_list(Run, await self._http.request("GET", "/runs", params=params))

    def iter(
        self,
        *,
        status: JobStatus | str | None = None,
        sample_id: uuid.UUID | str | None = None,
        page_size: int = MAX_PAGE_SIZE,
    ) -> AsyncIterator[Run]:
        return apaginate(
            lambda limit, offset: self.list(
                status=status, sample_id=sample_id, limit=limit, offset=offset
            ),
            page_size,
        )

    async def get(self, run_id: uuid.UUID | str) -> Run:
        return parse(Run, await self._http.request("GET", f"/runs/{run_id}"))

    async def launch(
        self,
        pipeline_id: str,
        *,
        sample_ids: Iterable[uuid.UUID | str] = (),
        pipeline_version: str = "latest",
        sequencing_run_id: uuid.UUID | str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> Run:
        """
        Launch an nf-core pipeline on samples whose FASTQ files are verified. Requires the
        ``bioinformatics_lead`` role in the workspace.

        Check ``run.execution_submitted``: when it is false, pipeline execution is disabled on
        the server and the run is recorded but will never run.
        """
        body = run_create_body(
            pipeline_id, sample_ids, pipeline_version, sequencing_run_id, parameters
        )
        return parse(Run, await self._http.request("POST", "/runs", json=body))

    async def wait(
        self,
        run_id: uuid.UUID | str,
        *,
        timeout: float | None = None,
        poll_interval: float = 15.0,
        raise_on_failure: bool = True,
    ) -> Run:
        """
        Poll the run until it succeeds, fails or is cancelled, and return it.

        Raises:
            ExecutionDisabledError: the server does not execute pipelines, so the run would
                stay ``pending`` forever.
            RunFailedError: the run failed or was cancelled (unless ``raise_on_failure=False``).
            RunTimeoutError: ``timeout`` seconds elapsed; the run keeps going on the server.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            run = await self.get(run_id)
            if finished(run, raise_on_failure=raise_on_failure):
                return run
            check_deadline(run, deadline, poll_interval, timeout)
            await asyncio.sleep(poll_interval)

    async def logs(self, run_id: uuid.UUID | str, *, after: int = -1) -> builtins.list[RunLogLine]:
        """Log lines with ``index > after`` (pass the last index you saw to get new lines)."""
        data = await self._http.request("GET", f"/runs/{run_id}/logs", params={"after": after})
        return parse_list(RunLogLine, data)

    async def stream_logs(self, run_id: uuid.UUID | str) -> AsyncIterator[RunEvent]:
        """
        Follow a run live (server-sent events) until it ends: ``async for event in ...``.
        The server closes the stream when the run finishes, was never submitted, or after an
        hour.
        """
        decoder = SSEDecoder()
        async with self._http.stream("GET", f"/runs/{run_id}/logs/stream") as response:
            async for line in response.aiter_lines():
                event = decoder.feed(line)
                if event is not None:
                    yield event
                    if decoder.ended:
                        return


class AsyncResults(AsyncResource):
    async def list(
        self,
        *,
        run_id: uuid.UUID | str | None = None,
        file_type: OutputFileType | str | None = None,
    ) -> builtins.list[ResultFile]:
        params = {"runId": run_id, "fileType": file_type}
        return parse_list(ResultFile, await self._http.request("GET", "/results", params=params))

    async def for_run(self, run_id: uuid.UUID | str) -> builtins.list[ResultFile]:
        """Outputs of one run, read from its output directory."""
        return parse_list(ResultFile, await self._http.request("GET", f"/results/runs/{run_id}"))

    async def download_url(self, output_id: uuid.UUID | str) -> ResultDownload:
        """A short-lived signed URL. Treat it as a secret until it expires."""
        data = await self._http.request("GET", f"/results/{output_id}/download")
        return parse(ResultDownload, data)

    async def download(self, output_id: uuid.UUID | str, dest: str | Path) -> Path:
        """
        Download a result file. ``dest`` is a file path, or an existing directory to save it
        under its own name. The MD5 is checked when the server knows it, and the file only
        appears at ``dest`` once complete.

        Raises:
            ChecksumMismatchError: the downloaded bytes do not match the recorded MD5; nothing
                is left at ``dest``.
        """
        link = await self.download_url(output_id)
        target = await asyncio.to_thread(download_target, dest, link)
        digest = hashlib.md5(usedforsecurity=False)
        fd, tmp_name = await asyncio.to_thread(
            tempfile.mkstemp, prefix=".titerlane-", dir=target.parent
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                async with self._http.storage_get(link.download_url) as resp:
                    async for chunk in resp.aiter_bytes():
                        digest.update(chunk)
                        await asyncio.to_thread(handle.write, chunk)
            check_download(link, digest.hexdigest())
            await asyncio.to_thread(tmp_path.replace, target)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        return target
