"""The asynchronous Titerlane Biologics API client."""

from __future__ import annotations

import os
from types import TracebackType
from typing import Any

import httpx

from titerlane._http import AsyncTransport
from titerlane.client import ENV_TOKEN, ENV_URL, ENV_WORKSPACE
from titerlane.errors import ConfigurationError
from titerlane.models import Token
from titerlane.resources.aio import (
    AsyncAuth,
    AsyncFastq,
    AsyncMembers,
    AsyncPipelines,
    AsyncResults,
    AsyncRuns,
    AsyncSamples,
    AsyncSequencingRuns,
    AsyncWorkspaces,
)


class AsyncClient:
    """
    Asynchronous client for one Titerlane Biologics server, for asyncio applications (web
    services, notebooks with a running loop, concurrent transfers).

    It has the same resources and methods as :class:`titerlane.Client`, awaited; listings and
    log streams are async iterators. Configuration is the same (arguments, else
    ``TITERLANE_URL``, ``TITERLANE_TOKEN``, ``TITERLANE_WORKSPACE``)::

        from titerlane import AsyncClient

        async with AsyncClient() as client:
            async for sample in client.samples.iter(status="fastq_received"):
                print(sample.sample_code)
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        token: str | None = None,
        workspace: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
        _http: AsyncTransport | None = None,
    ) -> None:
        if _http is not None:
            self._http = _http
        else:
            self._http = AsyncTransport(
                base_url or os.environ.get(ENV_URL, ""),
                token if token is not None else os.environ.get(ENV_TOKEN),
                workspace if workspace is not None else os.environ.get(ENV_WORKSPACE),
                timeout=timeout,
                max_retries=max_retries,
                transport=transport,
            )
        self.auth = AsyncAuth(self._http)
        self.workspaces = AsyncWorkspaces(self._http)
        self.members = AsyncMembers(self._http)
        self.samples = AsyncSamples(self._http)
        self.sequencing_runs = AsyncSequencingRuns(self._http)
        self.fastq = AsyncFastq(self._http)
        self.pipelines = AsyncPipelines(self._http)
        self.runs = AsyncRuns(self._http)
        self.results = AsyncResults(self._http)

    @classmethod
    async def login(
        cls,
        email: str,
        password: str,
        *,
        base_url: str | None = None,
        workspace: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> AsyncClient:
        """
        Sign in with email and password. The session expires after the server's JWT lifetime
        (one hour by default): prefer a personal access token for scripts and jobs.
        """
        anonymous = cls(
            base_url,
            token="",
            workspace=workspace,
            timeout=timeout,
            max_retries=max_retries,
            transport=transport,
        )
        try:
            data = await anonymous._http.request(
                "POST", "/auth/login", tenant=False, json={"email": email, "password": password}
            )
        except BaseException:
            await anonymous.close()
            raise
        anonymous._http.token = Token.model_validate(data).access_token
        return anonymous

    @property
    def base_url(self) -> str:
        return self._http.base_url

    @property
    def workspace(self) -> str | None:
        return self._http.workspace

    def with_workspace(self, workspace: str) -> AsyncClient:
        """A client for another workspace, sharing this one's connection and credentials."""
        if not workspace:
            raise ConfigurationError("workspace must not be empty")
        return AsyncClient(_http=self._http.bound_to(workspace))

    async def health(self) -> dict[str, Any]:
        """Server liveness. Needs no credentials."""
        data: dict[str, Any] = await self._http.request(
            "GET", "/health", tenant=False, versioned=False
        )
        return data

    async def close(self) -> None:
        await self._http.close()

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    def __repr__(self) -> str:
        # Never the token.
        return f"AsyncClient(base_url={self.base_url!r}, workspace={self.workspace!r})"
