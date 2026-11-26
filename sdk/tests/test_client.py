"""Client configuration, headers, errors and retries."""

from __future__ import annotations

import httpx
import pytest
from fakes import BASE_URL, TOKEN, WORKSPACE, FakeServer, body_of, ok, sample_json

from titerlane import (
    APIConnectionError,
    AuthenticationError,
    Client,
    ConfigurationError,
    NotFoundError,
    PermissionDeniedError,
    ServerError,
    UnprocessableError,
)


def test_sends_auth_workspace_and_user_agent(client: Client, server: FakeServer) -> None:
    server.on("GET", "/api/v1/samples", ok([]))
    client.samples.list()

    request = server.last("GET", "/api/v1/samples")
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.headers["X-Titerlane-Workspace"] == WORKSPACE
    assert request.headers["User-Agent"].startswith("titerlane-biologics-sdk/")


def test_user_routes_do_not_send_workspace(client: Client, server: FakeServer) -> None:
    server.on("GET", "/api/v1/workspaces", ok([]))
    client.workspaces.list()
    assert "X-Titerlane-Workspace" not in server.last("GET", "/api/v1/workspaces").headers


def test_missing_workspace_fails_before_any_request(server: FakeServer) -> None:
    with (
        Client(BASE_URL, token=TOKEN, transport=httpx.MockTransport(server)) as client,
        pytest.raises(ConfigurationError, match="with_workspace"),
    ):
        client.samples.list()
    assert server.requests == []


def test_with_workspace_switches_tenant(client: Client, server: FakeServer) -> None:
    server.on("GET", "/api/v1/samples", ok([]))
    east = client.with_workspace("lab-east")
    east.samples.list()
    assert server.last("GET", "/api/v1/samples").headers["X-Titerlane-Workspace"] == "lab-east"
    assert client.workspace == WORKSPACE


def test_reads_configuration_from_environment(
    server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TITERLANE_URL", BASE_URL + "/")
    monkeypatch.setenv("TITERLANE_TOKEN", "lcb_pat_from_env")
    monkeypatch.setenv("TITERLANE_WORKSPACE", "lab-env")
    server.on("GET", "/api/v1/samples", ok([]))
    with Client(transport=httpx.MockTransport(server)) as client:
        client.samples.list()
    request = server.last("GET", "/api/v1/samples")
    assert str(request.url).startswith(BASE_URL + "/api/v1/samples")
    assert request.headers["Authorization"] == "Bearer lcb_pat_from_env"
    assert request.headers["X-Titerlane-Workspace"] == "lab-env"


def test_missing_base_url_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="TITERLANE_URL"):
        Client(token=TOKEN)


def test_repr_and_errors_never_show_the_token(client: Client, server: FakeServer) -> None:
    server.on("GET", "/api/v1/auth/me", ok({"detail": "Could not validate credentials"}, 401))
    assert TOKEN not in repr(client)
    with pytest.raises(AuthenticationError) as exc_info:
        client.auth.me()
    assert TOKEN not in str(exc_info.value)
    assert exc_info.value.status_code == 401


@pytest.mark.parametrize(
    ("status", "error"),
    [(403, PermissionDeniedError), (404, NotFoundError), (500, ServerError)],
)
def test_maps_status_to_exception(
    client: Client, server: FakeServer, status: int, error: type[Exception]
) -> None:
    server.on("GET", "/api/v1/samples/abc", ok({"detail": "nope"}, status))
    with pytest.raises(error, match="nope"):
        client.samples.get("abc")


def test_validation_detail_is_readable(client: Client, server: FakeServer) -> None:
    detail = [{"loc": ["body", "sampleCode"], "msg": "Field required", "type": "missing"}]
    server.on("POST", "/api/v1/samples", ok({"detail": detail}, 422))
    with pytest.raises(UnprocessableError) as exc_info:
        client.samples.create(sample_code="S", modality="genomics")
    assert "sampleCode: Field required" in str(exc_info.value)
    assert exc_info.value.detail == detail


def test_get_is_retried_on_unavailable(
    client: Client, server: FakeServer, no_sleep: list[float]
) -> None:
    server.on("GET", "/api/v1/samples", ok({}, 503), ok({}, 502), ok([sample_json()]))
    assert len(client.samples.list()) == 1
    assert len(server.requests) == 3
    assert no_sleep == [0.5, 1.0]


def test_post_is_never_retried(client: Client, server: FakeServer) -> None:
    server.on("POST", "/api/v1/samples", ok({"detail": "busy"}, 503))
    with pytest.raises(ServerError):
        client.samples.create(sample_code="S", modality="genomics")
    assert len(server.requests) == 1


def test_network_failure_raises_connection_error(server: FakeServer) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with (
        Client(
            BASE_URL, token=TOKEN, workspace=WORKSPACE, transport=httpx.MockTransport(refuse)
        ) as c,
        pytest.raises(APIConnectionError, match="Could not reach"),
    ):
        c.samples.list()


def test_login_uses_password_then_bearer(server: FakeServer) -> None:
    server.on("POST", "/api/v1/auth/login", ok({"accessToken": "jwt-1", "expiresIn": 3600}))
    server.on("GET", "/api/v1/workspaces", ok([]))
    with Client.login(
        "lead@lab.example", "secret-pass", base_url=BASE_URL, transport=httpx.MockTransport(server)
    ) as client:
        client.workspaces.list()

    login = server.last("POST", "/api/v1/auth/login")
    assert "Authorization" not in login.headers
    assert body_of(login) == {"email": "lead@lab.example", "password": "secret-pass"}
    assert server.last("GET", "/api/v1/workspaces").headers["Authorization"] == "Bearer jwt-1"


def test_health_is_unversioned(client: Client, server: FakeServer) -> None:
    server.on("GET", "/health", ok({"status": "ok"}))
    assert client.health() == {"status": "ok"}
