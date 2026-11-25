"""Fixtures for SDK unit tests."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fakes import BASE_URL, TOKEN, WORKSPACE, FakeServer

from labchain import Client


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
def client(server: FakeServer) -> Iterator[Client]:
    with Client(
        BASE_URL, token=TOKEN, workspace=WORKSPACE, transport=httpx.MockTransport(server)
    ) as c:
        yield c


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Retries and run polling never really wait in tests; the delays are recorded."""
    delays: list[float] = []
    monkeypatch.setattr("time.sleep", delays.append)
    return delays


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LABCHAIN_URL", "LABCHAIN_TOKEN", "LABCHAIN_WORKSPACE"):
        monkeypatch.delenv(name, raising=False)
