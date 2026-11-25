"""nf-core pipeline catalog and pipeline runs."""

from __future__ import annotations

import builtins
import time
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Literal

from labchain.errors import ExecutionDisabledError, RunFailedError, RunTimeoutError
from labchain.models import JobStatus, Pipeline, Run, RunCreate, RunLogLine
from labchain.resources._base import Resource, paginate, parse, parse_list

MAX_PAGE_SIZE = 1000


class Pipelines(Resource):
    def list(self) -> builtins.list[Pipeline]:
        """The nf-core pipelines this server can run, with their allowed versions."""
        return parse_list(Pipeline, self._http.request("GET", "/pipelines"))

    def get(self, pipeline_id: str) -> Pipeline:
        return parse(Pipeline, self._http.request("GET", f"/pipelines/{pipeline_id}"))


@dataclass(frozen=True)
class RunEvent:
    """
    One server-sent event of a run log stream.

    ``log``: a log line (``index`` is its position, usable with ``logs(after=...)``).
    ``status``: the run status changed (``data`` is the new status).
    ``end``: the stream is over (``data`` is the final status, or ``run-not-found``).
    """

    kind: Literal["log", "status", "end"]
    data: str
    index: int | None = None


class Runs(Resource):
    def list(
        self,
        *,
        status: JobStatus | str | None = None,
        sample_id: uuid.UUID | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[Run]:
        params = {"status": status, "sampleId": sample_id, "limit": limit, "offset": offset}
        return parse_list(Run, self._http.request("GET", "/runs", params=params))

    def iter(
        self,
        *,
        status: JobStatus | str | None = None,
        sample_id: uuid.UUID | str | None = None,
        page_size: int = MAX_PAGE_SIZE,
    ) -> Iterator[Run]:
        return paginate(
            lambda limit, offset: self.list(
                status=status, sample_id=sample_id, limit=limit, offset=offset
            ),
            page_size,
        )

    def get(self, run_id: uuid.UUID | str) -> Run:
        return parse(Run, self._http.request("GET", f"/runs/{run_id}"))

    def launch(
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
        body = RunCreate(
            pipeline_id=pipeline_id,
            pipeline_version=pipeline_version,
            sample_ids=[uuid.UUID(str(sample_id)) for sample_id in sample_ids],
            sequencing_run_id=uuid.UUID(str(sequencing_run_id)) if sequencing_run_id else None,
            parameters=parameters or {},
        ).to_json()
        return parse(Run, self._http.request("POST", "/runs", json=body))

    def wait(
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
            run = self.get(run_id)
            if not run.execution_submitted and not run.status.is_terminal:
                raise ExecutionDisabledError(
                    f"Run {run.id} was recorded but not submitted for execution: pipeline "
                    "execution is disabled on this server, so it will stay pending"
                )
            if run.status.is_terminal:
                if raise_on_failure and run.status != JobStatus.succeeded:
                    message = run.progress.get("errorMessage")
                    raise RunFailedError(str(run.id), run.status.value, message)
                return run
            if deadline is not None and time.monotonic() + poll_interval > deadline:
                raise RunTimeoutError(
                    f"Run {run.id} still {run.status.value} after {timeout} seconds"
                )
            time.sleep(poll_interval)

    def logs(self, run_id: uuid.UUID | str, *, after: int = -1) -> builtins.list[RunLogLine]:
        """Log lines with ``index > after`` (pass the last index you saw to get new lines)."""
        data = self._http.request("GET", f"/runs/{run_id}/logs", params={"after": after})
        return parse_list(RunLogLine, data)

    def stream_logs(self, run_id: uuid.UUID | str) -> Iterator[RunEvent]:
        """
        Follow a run live (server-sent events) until it ends. The server closes the stream
        when the run finishes, was never submitted, or after an hour.
        """
        with self._http.stream("GET", f"/runs/{run_id}/logs/stream") as response:
            yield from parse_sse(response.iter_lines())


EventKind = Literal["log", "status", "end"]
_EVENT_KINDS: dict[str, EventKind] = {"log": "log", "status": "status", "end": "end"}


def parse_sse(lines: Iterable[str]) -> Iterator[RunEvent]:
    """Decode a ``text/event-stream`` body into run events; stops after ``end``."""
    kind: str | None = None
    data: list[str] = []
    event_id: str | None = None
    for raw in lines:
        line = raw.rstrip("\r")
        if line == "":
            known = _EVENT_KINDS.get(kind or "")
            if known is not None:
                index = int(event_id) if event_id is not None and event_id.isdigit() else None
                yield RunEvent(kind=known, data="\n".join(data), index=index)
                if known == "end":
                    return
            kind, data, event_id = None, [], None
            continue
        if line.startswith(":"):
            continue  # comment / keep-alive ping
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "event":
            kind = value
        elif field == "data":
            data.append(value)
        elif field == "id":
            event_id = value
