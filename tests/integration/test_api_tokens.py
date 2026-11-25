"""Personal access tokens against a real database: lifecycle, RBAC, isolation, audit."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.api_token import ApiToken
from app.models.audit import AuditLog
from app.models.user import Role, User
from app.models.workspace import Workspace

TOKENS = "/api/v1/auth/tokens"
SAMPLE = {"sampleCode": "S-001", "modality": "genomics"}

MakeUser = Callable[..., Awaitable[User]]
MakeWorkspace = Callable[..., Awaitable[Workspace]]
Login = Callable[[str], Awaitable[dict[str, str]]]


def bearer(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


def ws(headers: dict[str, str], slug: str) -> dict[str, str]:
    return {**headers, "X-LabChain-Workspace": slug}


async def _create(client: httpx.AsyncClient, auth: dict[str, str], name: str = "ci") -> str:
    response = await client.post(TOKENS, json={"name": name, "expiresInDays": 30}, headers=auth)
    assert response.status_code == 201, response.text
    return str(response.json()["token"])


async def test_token_lifecycle_and_audit(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await make_user("alice@lab.io")
    await make_workspace("lab-west", {alice.id: Role.lab_technician})
    auth = await login("alice@lab.io")

    created = await client.post(
        TOKENS, json={"name": "  analysis notebook ", "expiresInDays": 30}, headers=auth
    )
    assert created.status_code == 201, created.text
    body = created.json()
    secret = body["token"]
    assert secret.startswith("lcb_pat_") and body["tokenPrefix"] == secret[:16]
    assert body["name"] == "analysis notebook"
    assert body["revokedAt"] is None and body["lastUsedAt"] is None

    # The token acts as Alice, with her workspace role, without any login.
    me = await client.get("/api/v1/auth/me", headers=bearer(secret))
    assert me.status_code == 200 and me.json()["email"] == "alice@lab.io"
    sample = await client.post(
        "/api/v1/samples", json=SAMPLE, headers=ws(bearer(secret), "lab-west")
    )
    assert sample.status_code == 201, sample.text

    listing = await client.get(TOKENS, headers=auth)
    assert listing.status_code == 200
    [listed] = listing.json()
    assert "token" not in listed and listed["lastUsedAt"] is not None

    revoked = await client.delete(f"{TOKENS}/{body['id']}", headers=auth)
    assert revoked.status_code == 200 and revoked.json()["revokedAt"] is not None
    assert (await client.get("/api/v1/auth/me", headers=bearer(secret))).status_code == 401
    again = await client.delete(f"{TOKENS}/{body['id']}", headers=auth)
    assert again.status_code == 409

    async with session_factory() as session:
        entries = (
            (
                await session.execute(
                    select(AuditLog)
                    .where(AuditLog.entity_type == "api_token")
                    .order_by(AuditLog.created_at)
                )
            )
            .scalars()
            .all()
        )
        stored = (await session.execute(select(ApiToken))).scalar_one()
    assert [entry.action for entry in entries] == ["create", "revoke"]
    assert all(entry.actor_id == alice.id for entry in entries)
    for entry in entries:
        payload = repr(entry.before_state) + repr(entry.after_state)
        assert secret not in payload and stored.token_hash not in payload
    assert stored.token_hash != secret


async def test_token_keeps_per_workspace_roles_and_isolation(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
) -> None:
    alice = await make_user("alice@lab.io")
    bob = await make_user("bob@lab.io")
    await make_workspace("lab-west", {alice.id: Role.lab_technician})
    await make_workspace("lab-east", {bob.id: Role.bioinformatics_lead})
    token = bearer(await _create(client, await login("alice@lab.io")))

    # Alice is a technician in lab-west: launching a run is still forbidden.
    run = await client.post(
        "/api/v1/runs",
        json={"pipelineId": "rnaseq", "sampleIds": []},
        headers=ws(token, "lab-west"),
    )
    assert run.status_code == 403

    # Bob's workspace stays invisible, as with a login JWT.
    foreign = await client.get("/api/v1/samples", headers=ws(token, "lab-east"))
    assert foreign.status_code == 404
    assert foreign.json()["detail"] == "Workspace 'lab-east' not found"


async def test_tokens_are_private_to_their_owner(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    login: Login,
) -> None:
    await make_user("alice@lab.io")
    await make_user("bob@lab.io")
    alice_auth = await login("alice@lab.io")
    bob_auth = await login("bob@lab.io")
    created = await client.post(TOKENS, json={"name": "ci"}, headers=alice_auth)
    token_id = created.json()["id"]

    assert (await client.get(TOKENS, headers=bob_auth)).json() == []
    stolen = await client.delete(f"{TOKENS}/{token_id}", headers=bob_auth)
    assert stolen.status_code == 404
    assert stolen.json()["detail"] == f"API token {token_id} not found"


async def test_token_cannot_create_tokens_but_can_revoke_itself(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    login: Login,
) -> None:
    await make_user("alice@lab.io")
    secret = await _create(client, await login("alice@lab.io"))

    minted = await client.post(TOKENS, json={"name": "escalate"}, headers=bearer(secret))
    assert minted.status_code == 403

    [own] = (await client.get(TOKENS, headers=bearer(secret))).json()
    revoked = await client.delete(f"{TOKENS}/{own['id']}", headers=bearer(secret))
    assert revoked.status_code == 200
    assert (await client.get(TOKENS, headers=bearer(secret))).status_code == 401


async def test_create_validation_errors(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    login: Login,
) -> None:
    await make_user("alice@lab.io")
    auth = await login("alice@lab.io")
    for payload in (
        {"name": "   "},
        {"name": "ci", "expiresInDays": 0},
        {"name": "ci", "expiresInDays": 100_000},
        {},
    ):
        response = await client.post(TOKENS, json=payload, headers=auth)
        assert response.status_code == 422, payload
    assert (await client.get(TOKENS, headers=auth)).json() == []


async def test_expired_token_and_inactive_owner_are_rejected(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    login: Login,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await make_user("alice@lab.io")
    await make_user("bob@lab.io")
    expired = await _create(client, await login("alice@lab.io"))
    inactive = await _create(client, await login("bob@lab.io"))

    async with session_factory() as session:
        await session.execute(
            update(ApiToken)
            .where(ApiToken.user_id == alice.id)
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await session.execute(
            update(User).where(User.email == "bob@lab.io").values(is_active=False)
        )
        await session.commit()

    assert (await client.get("/api/v1/auth/me", headers=bearer(expired))).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=bearer(inactive))).status_code == 401
    unknown = bearer("lcb_pat_" + "x" * 43)
    assert (await client.get("/api/v1/auth/me", headers=unknown)).status_code == 401
