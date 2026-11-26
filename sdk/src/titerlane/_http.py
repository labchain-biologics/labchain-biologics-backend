"""
HTTP layer: headers, error mapping, retries. Never logs credentials or signed URLs.

``Transport`` (``httpx.Client``) and ``AsyncTransport`` (``httpx.AsyncClient``) share every
decision (headers, URLs, which requests are retried, how errors are mapped) through
``_TransportBase``; they differ only in how they wait for I/O.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Self

import httpx

from titerlane._version import __version__
from titerlane.errors import APIConnectionError, ConfigurationError, error_for_status

logger = logging.getLogger("titerlane")

API_PREFIX = "/api/v1"
WORKSPACE_HEADER = "X-Titerlane-Workspace"
USER_AGENT = f"titerlane-biologics-sdk/{__version__}"
# Retried on idempotent requests only: the request may have reached a briefly unavailable server.
RETRY_STATUSES = frozenset({502, 503, 504})
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

Params = Mapping[str, Any]


def _clean_params(params: Params | None) -> dict[str, Any] | None:
    """Drop unset filters and send enums/UUIDs as strings."""
    if params is None:
        return None
    return {key: str(value) for key, value in params.items() if value is not None}


class _TransportBase:
    """Configuration and request decisions shared by the sync and async transports."""

    def __init__(
        self, base_url: str, token: str | None, workspace: str | None, *, max_retries: int
    ) -> None:
        if not base_url:
            raise ConfigurationError("base_url is required (or set TITERLANE_URL)")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.workspace = workspace
        self.max_retries = max_retries
        self._owns_client = True

    def bound_to(self, workspace: str) -> Self:
        """Same connection and credentials, another workspace. Closing it closes nothing."""
        clone = object.__new__(type(self))
        clone.__dict__.update(self.__dict__)
        clone.workspace = workspace
        clone._owns_client = False
        return clone

    def _headers(self, *, tenant: bool) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if tenant:
            if not self.workspace:
                raise ConfigurationError(
                    "This call is scoped to a workspace: pass workspace= to the client, set "
                    "TITERLANE_WORKSPACE, or use client.with_workspace('<slug>')"
                )
            headers[WORKSPACE_HEADER] = self.workspace
        return headers

    def _url(self, path: str, *, versioned: bool = True) -> str:
        return f"{self.base_url}{API_PREFIX if versioned else ''}{path}"

    def _attempts(self, method: str) -> int:
        return 1 + (self.max_retries if method in IDEMPOTENT_METHODS else 0)

    def _connection_error(self, exc: httpx.TransportError) -> APIConnectionError:
        return APIConnectionError(f"Could not reach {self.base_url}: {type(exc).__name__}")


class Transport(_TransportBase):
    """Authenticated, synchronous access to one Titerlane API, optionally bound to a workspace."""

    def __init__(
        self,
        base_url: str,
        token: str | None,
        workspace: str | None,
        *,
        timeout: float,
        max_retries: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(base_url, token, workspace, max_retries=max_retries)
        self._client = httpx.Client(timeout=timeout, transport=transport)
        # Signed object-storage URLs carry their own authorization: they must never receive the
        # API bearer token, so they go through a separate client that has no credentials.
        self._storage = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
            self._storage.close()

    # --- API requests ----------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        tenant: bool = True,
        params: Params | None = None,
        json: Any = None,
        files: Mapping[str, Any] | None = None,
        versioned: bool = True,
    ) -> Any:
        """Send a request and return the decoded JSON body (``None`` for 204)."""
        headers = self._headers(tenant=tenant)
        attempts = self._attempts(method)
        for attempt in range(1, attempts + 1):
            logger.debug("%s %s (attempt %d)", method, path, attempt)
            try:
                response = self._client.request(
                    method,
                    self._url(path, versioned=versioned),
                    headers=headers,
                    params=_clean_params(params),
                    json=json,
                    files=files,
                )
            except httpx.TransportError as exc:
                if attempt < attempts:
                    time.sleep(backoff_delay(attempt))
                    continue
                raise self._connection_error(exc) from exc
            if response.status_code in RETRY_STATUSES and attempt < attempts:
                time.sleep(backoff_delay(attempt))
                continue
            raise_for_status(response, method, path)
            return decode(response)
        raise AssertionError("unreachable")  # pragma: no cover

    @contextmanager
    def stream(
        self, method: str, path: str, *, params: Params | None = None
    ) -> Iterator[httpx.Response]:
        """Streamed API response (server-sent events). No read timeout: the server paces it."""
        headers = {**self._headers(tenant=True), "Accept": "text/event-stream"}
        try:
            with self._client.stream(
                method,
                self._url(path),
                headers=headers,
                params=_clean_params(params),
                timeout=httpx.Timeout(self._client.timeout.connect, read=None),
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    raise_for_status(response, method, path)
                yield response
        except httpx.TransportError as exc:
            raise APIConnectionError(
                f"Lost connection to {self.base_url}: {type(exc).__name__}"
            ) from exc

    # --- Signed object-storage URLs --------------------------------------------------------

    def storage_put(self, url: str, content: Any, headers: Mapping[str, str]) -> None:
        try:
            response = self._storage.put(url, content=content, headers=dict(headers))
        except httpx.TransportError as exc:
            raise APIConnectionError(f"Upload failed: {type(exc).__name__}") from exc
        raise_for_storage_status(response, "upload")

    @contextmanager
    def storage_get(self, url: str) -> Iterator[httpx.Response]:
        try:
            with self._storage.stream("GET", url) as response:
                if response.status_code >= 400:
                    response.read()
                    raise_for_storage_status(response, "download")
                yield response
        except httpx.TransportError as exc:
            raise APIConnectionError(f"Download failed: {type(exc).__name__}") from exc


class AsyncTransport(_TransportBase):
    """The asynchronous counterpart of :class:`Transport`, on ``httpx.AsyncClient``."""

    def __init__(
        self,
        base_url: str,
        token: str | None,
        workspace: str | None,
        *,
        timeout: float,
        max_retries: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(base_url, token, workspace, max_retries=max_retries)
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)
        # Same rule as the sync transport: signed URLs never see the API credentials.
        self._storage = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
            await self._storage.aclose()

    # --- API requests ----------------------------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        tenant: bool = True,
        params: Params | None = None,
        json: Any = None,
        files: Mapping[str, Any] | None = None,
        versioned: bool = True,
    ) -> Any:
        """Send a request and return the decoded JSON body (``None`` for 204)."""
        headers = self._headers(tenant=tenant)
        attempts = self._attempts(method)
        for attempt in range(1, attempts + 1):
            logger.debug("%s %s (attempt %d)", method, path, attempt)
            try:
                response = await self._client.request(
                    method,
                    self._url(path, versioned=versioned),
                    headers=headers,
                    params=_clean_params(params),
                    json=json,
                    files=files,
                )
            except httpx.TransportError as exc:
                if attempt < attempts:
                    await asyncio.sleep(backoff_delay(attempt))
                    continue
                raise self._connection_error(exc) from exc
            if response.status_code in RETRY_STATUSES and attempt < attempts:
                await asyncio.sleep(backoff_delay(attempt))
                continue
            raise_for_status(response, method, path)
            return decode(response)
        raise AssertionError("unreachable")  # pragma: no cover

    @asynccontextmanager
    async def stream(
        self, method: str, path: str, *, params: Params | None = None
    ) -> AsyncIterator[httpx.Response]:
        """Streamed API response (server-sent events). No read timeout: the server paces it."""
        headers = {**self._headers(tenant=True), "Accept": "text/event-stream"}
        try:
            async with self._client.stream(
                method,
                self._url(path),
                headers=headers,
                params=_clean_params(params),
                timeout=httpx.Timeout(self._client.timeout.connect, read=None),
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise_for_status(response, method, path)
                yield response
        except httpx.TransportError as exc:
            raise APIConnectionError(
                f"Lost connection to {self.base_url}: {type(exc).__name__}"
            ) from exc

    # --- Signed object-storage URLs --------------------------------------------------------

    async def storage_put(self, url: str, content: Any, headers: Mapping[str, str]) -> None:
        try:
            response = await self._storage.put(url, content=content, headers=dict(headers))
        except httpx.TransportError as exc:
            raise APIConnectionError(f"Upload failed: {type(exc).__name__}") from exc
        raise_for_storage_status(response, "upload")

    @asynccontextmanager
    async def storage_get(self, url: str) -> AsyncIterator[httpx.Response]:
        try:
            async with self._storage.stream("GET", url) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise_for_storage_status(response, "download")
                yield response
        except httpx.TransportError as exc:
            raise APIConnectionError(f"Download failed: {type(exc).__name__}") from exc


# --- Shared response handling --------------------------------------------------------------


def decode(response: httpx.Response) -> Any:
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def raise_for_status(response: httpx.Response, method: str, path: str) -> None:
    if response.status_code < 400:
        return
    try:
        body = response.json()
        detail = body.get("detail", body) if isinstance(body, dict) else body
    except ValueError:
        detail = response.text[:500] or response.reason_phrase
    raise error_for_status(response.status_code, detail, method=method, path=path)


def raise_for_storage_status(response: httpx.Response, action: str) -> None:
    if response.status_code < 400:
        return
    # The URL is a credential: report the status and storage error code only.
    raise APIConnectionError(
        f"Object storage rejected the {action} ({response.status_code}): "
        f"{_storage_error_code(response)}"
    )


def _storage_error_code(response: httpx.Response) -> str:
    text = response.text
    start, end = text.find("<Code>"), text.find("</Code>")
    if start != -1 and end > start:
        return text[start + len("<Code>") : end]
    return response.reason_phrase


def backoff_delay(attempt: int) -> float:
    return float(min(0.5 * 2 ** (attempt - 1), 4.0))
