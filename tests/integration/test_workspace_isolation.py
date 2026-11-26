"""Tenant isolation and membership management against a real database."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.audit import AuditLog
from app.models.user import Role, User
from app.models.workspace import Workspace

SAMPLE = {"sampleCode": "S-001", "modality": "genomics"}

MakeUser = Callable[..., Awaitable[User]]
MakeWorkspace = Callable[..., Awaitable[Workspace]]
Login = Callable[[str], Awaitable[dict[str, str]]]


def ws(headers: dict[str, str], slug: str) -> dict[str, str]:
    return {**headers, "X-Titerlane-Workspace": slug}


async def test_login_does_not_need_workspace_and_me_lists_memberships(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
) -> None:
    alice = await make_user("alice@lab.io")
    await make_workspace("lab-west", {alice.id: Role.bioinformatics_lead})
    await make_workspace("lab-east", {alice.id: Role.lab_technician})
    await make_workspace("lab-north", {})

    me = await client.get("/api/v1/auth/me", headers=await login("alice@lab.io"))

    assert me.status_code == 200
    body = me.json()
    assert "role" not in body
    assert {(m["slug"], m["role"]) for m in body["memberships"]} == {
        ("lab-west", "bioinformatics_lead"),
        ("lab-east", "lab_technician"),
    }


async def test_user_cannot_read_or_write_another_workspace(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
) -> None:
    alice = await make_user("alice@lab.io")
    bob = await make_user("bob@lab.io")
    await make_workspace("lab-west", {alice.id: Role.bioinformatics_lead})
    await make_workspace("lab-east", {bob.id: Role.bioinformatics_lead})
    alice_auth = await login("alice@lab.io")
    bob_auth = await login("bob@lab.io")

    created = await client.post("/api/v1/samples", json=SAMPLE, headers=ws(bob_auth, "lab-east"))
    assert created.status_code == 201, created.text
    sample_id = created.json()["id"]

    # Alice forging Bob's workspace header gets the same 404 as for a non-existent workspace.
    for path in ("/api/v1/samples", f"/api/v1/samples/{sample_id}", "/api/v1/runs"):
        foreign = await client.get(path, headers=ws(alice_auth, "lab-east"))
        missing = await client.get(path, headers=ws(alice_auth, "does-not-exist"))
        assert foreign.status_code == 404
        assert missing.status_code == 404
        assert foreign.json()["detail"] == "Workspace 'lab-east' not found"

    write = await client.post("/api/v1/samples", json=SAMPLE, headers=ws(alice_auth, "lab-east"))
    assert write.status_code == 404

    # In her own workspace, Bob's sample is invisible.
    own = await client.get(f"/api/v1/samples/{sample_id}", headers=ws(alice_auth, "lab-west"))
    assert own.status_code == 404
    listing = await client.get("/api/v1/samples", headers=ws(alice_auth, "lab-west"))
    assert listing.json() == []


async def test_role_is_per_workspace(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
) -> None:
    alice = await make_user("alice@lab.io")
    await make_workspace("lab-west", {alice.id: Role.bioinformatics_lead})
    await make_workspace("lab-east", {alice.id: Role.lab_technician})
    auth = await login("alice@lab.io")
    payload = {"pipelineId": "rnaseq", "sampleIds": []}

    as_tech = await client.post("/api/v1/runs", json=payload, headers=ws(auth, "lab-east"))
    assert as_tech.status_code == 403

    # Past the role check, the request fails on its content (no samples), not on RBAC.
    as_lead = await client.post("/api/v1/runs", json=payload, headers=ws(auth, "lab-west"))
    assert as_lead.status_code == 422, as_lead.text


async def test_create_workspace_makes_creator_lead_and_audits(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    login: Login,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await make_user("alice@lab.io")
    auth = await login("alice@lab.io")

    created = await client.post(
        "/api/v1/workspaces", json={"slug": "helix-genomics", "name": "Helix"}, headers=auth
    )
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "bioinformatics_lead"

    duplicate = await client.post(
        "/api/v1/workspaces", json={"slug": "helix-genomics", "name": "Other"}, headers=auth
    )
    assert duplicate.status_code == 409

    invalid = await client.post(
        "/api/v1/workspaces", json={"slug": "Helix Genomics", "name": "Bad"}, headers=auth
    )
    assert invalid.status_code == 422

    async with session_factory() as session:
        actions = (
            await session.execute(
                select(AuditLog.action).where(AuditLog.workspace == "helix-genomics")
            )
        ).scalars()
        assert set(actions) == {"create", "add_member"}


async def test_member_management(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
) -> None:
    lead = await make_user("lead@lab.io")
    tech = await make_user("tech@lab.io")
    await make_user("new@lab.io")
    await make_workspace(
        "lab-west", {lead.id: Role.bioinformatics_lead, tech.id: Role.lab_technician}
    )
    lead_h = ws(await login("lead@lab.io"), "lab-west")
    tech_h = ws(await login("tech@lab.io"), "lab-west")

    listing = await client.get("/api/v1/members", headers=tech_h)
    assert listing.status_code == 200
    assert {m["email"] for m in listing.json()} == {"lead@lab.io", "tech@lab.io"}

    forbidden = await client.post("/api/v1/members", json={"email": "new@lab.io"}, headers=tech_h)
    assert forbidden.status_code == 403

    added = await client.post("/api/v1/members", json={"email": "new@lab.io"}, headers=lead_h)
    assert added.status_code == 201
    assert added.json()["role"] == "lab_technician"

    again = await client.post("/api/v1/members", json={"email": "new@lab.io"}, headers=lead_h)
    assert again.status_code == 409

    unknown = await client.post("/api/v1/members", json={"email": "nobody@lab.io"}, headers=lead_h)
    assert unknown.status_code == 404

    # The last lead can neither be demoted nor removed.
    demote = await client.patch(
        f"/api/v1/members/{lead.id}", json={"role": "lab_technician"}, headers=lead_h
    )
    assert demote.status_code == 409
    remove_last = await client.delete(f"/api/v1/members/{lead.id}", headers=lead_h)
    assert remove_last.status_code == 409

    promote = await client.patch(
        f"/api/v1/members/{tech.id}", json={"role": "bioinformatics_lead"}, headers=lead_h
    )
    assert promote.status_code == 200
    removed = await client.delete(f"/api/v1/members/{lead.id}", headers=lead_h)
    assert removed.status_code == 204

    # Once removed, the former lead has no access at all.
    after = await client.get("/api/v1/samples", headers=lead_h)
    assert after.status_code == 404


async def test_inactive_workspace_is_unreachable(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await make_user("alice@lab.io")
    workspace = await make_workspace("lab-west", {alice.id: Role.bioinformatics_lead})
    async with session_factory() as session:
        stored = await session.get(Workspace, workspace.id)
        assert stored is not None
        stored.is_active = False
        await session.commit()

    response = await client.get(
        "/api/v1/samples", headers=ws(await login("alice@lab.io"), "lab-west")
    )
    assert response.status_code == 404
