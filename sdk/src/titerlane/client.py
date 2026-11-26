"""The Titerlane Biologics API client."""

from __future__ import annotations

import os
from types import TracebackType
from typing import Any

import httpx

from titerlane._http import Transport
from titerlane.errors import ConfigurationError
from titerlane.models import Token
from titerlane.resources import (
    Auth,
    Fastq,
    Members,
    Pipelines,
    Results,
    Runs,
    Samples,
    SequencingRuns,
    Workspaces,
)

ENV_URL = "TITERLANE_URL"
ENV_TOKEN = "TITERLANE_TOKEN"  # noqa: S105 - name of an environment variable, not a secret
ENV_WORKSPACE = "TITERLANE_WORKSPACE"


class Client:
    """
    Synchronous client for one Titerlane Biologics server.

    Arguments left out are read from the environment: ``TITERLANE_URL``, ``TITERLANE_TOKEN``
    (a personal access token, ``lcb_pat_...``) and ``TITERLANE_WORKSPACE`` (the workspace slug
    used by workspace-scoped calls)::

        from titerlane import Client

        with Client() as client:
            for sample in client.samples.iter(status="fastq_received"):
                print(sample.sample_code)

    Every call acts as the token's owner, with their role in the selected workspace; the
    server enforces permissions.
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        token: str | None = None,
        workspace: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
        _http: Transport | None = None,
    ) -> None:
        if _http is not None:
            self._http = _http
        else:
            self._http = Transport(
                base_url or os.environ.get(ENV_URL, ""),
                token if token is not None else os.environ.get(ENV_TOKEN),
                workspace if workspace is not None else os.environ.get(ENV_WORKSPACE),
                timeout=timeout,
                max_retries=max_retries,
                transport=transport,
            )
        self.auth = Auth(self._http)
        self.workspaces = Workspaces(self._http)
        self.members = Members(self._http)
        self.samples = Samples(self._http)
        self.sequencing_runs = SequencingRuns(self._http)
        self.fastq = Fastq(self._http)
        self.pipelines = Pipelines(self._http)
        self.runs = Runs(self._http)
        self.results = Results(self._http)

    @classmethod
    def login(
        cls,
        email: str,
        password: str,
        *,
        base_url: str | None = None,
        workspace: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> Client:
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
            data = anonymous._http.request(
                "POST", "/auth/login", tenant=False, json={"email": email, "password": password}
            )
        except BaseException:
            anonymous.close()
            raise
        anonymous._http.token = Token.model_validate(data).access_token
        return anonymous

    @property
    def base_url(self) -> str:
        return self._http.base_url

    @property
    def workspace(self) -> str | None:
        return self._http.workspace

    def with_workspace(self, workspace: str) -> Client:
        """A client for another workspace, sharing this one's connection and credentials."""
        if not workspace:
            raise ConfigurationError("workspace must not be empty")
        return Client(_http=self._http.bound_to(workspace))

    def health(self) -> dict[str, Any]:
        """Server liveness. Needs no credentials."""
        data: dict[str, Any] = self._http.request("GET", "/health", tenant=False, versioned=False)
        return data

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        # Never the token.
        return f"Client(base_url={self.base_url!r}, workspace={self.workspace!r})"
