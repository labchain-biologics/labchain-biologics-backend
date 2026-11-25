"""Sample deletion is a soft delete: hidden from the API, kept in the database and audited."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.audit import AuditLog
from app.models.pipeline import FastqFile
from app.models.sample import Sample
from app.models.user import Role, User
from app.models.workspace import Workspace
from tests.integration.conftest import FakeS3

MakeUser = Callable[..., Awaitable[User]]
MakeWorkspace = Callable[..., Awaitable[Workspace]]
Login = Callable[[str], Awaitable[dict[str, str]]]


def ws(headers: dict[str, str], slug: str) -> dict[str, str]:
    return {**headers, "X-LabChain-Workspace": slug}


async def _setup(
    make_user: MakeUser, make_workspace: MakeWorkspace, login: Login
) -> tuple[dict[str, str], dict[str, str]]:
    tech = await make_user("tech@lab.io")
    other = await make_user("other@lab.io")
    await make_workspace("lab-west", {tech.id: Role.lab_technician})
    await make_workspace("lab-east", {other.id: Role.lab_technician})
    return (
        ws(await login("tech@lab.io"), "lab-west"),
        ws(await login("other@lab.io"), "lab-east"),
    )


async def _create(client: httpx.AsyncClient, headers: dict[str, str], code: str) -> str:
    response = await client.post(
        "/api/v1/samples", json={"sampleCode": code, "modality": "genomics"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def test_delete_hides_sample_but_keeps_row_links_and_audit(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    session_factory: async_sessionmaker[AsyncSession],
    fake_s3: FakeS3,
) -> None:
    headers, _ = await _setup(make_user, make_workspace, login)
    sample_id = await _create(client, headers, "S-001")
    fastq = await client.post(
        "/api/v1/fastq/register",
        json={"filename": "S-001_R1.fastq.gz", "sampleId": sample_id},
        headers=headers,
    )
    assert fastq.status_code == 201, fastq.text

    deleted = await client.delete(f"/api/v1/samples/{sample_id}", headers=headers)
    assert deleted.status_code == 204

    assert (await client.get(f"/api/v1/samples/{sample_id}", headers=headers)).status_code == 404
    assert (await client.get("/api/v1/samples", headers=headers)).json() == []
    again = await client.delete(f"/api/v1/samples/{sample_id}", headers=headers)
    assert again.status_code == 404
    patch = await client.patch(f"/api/v1/samples/{sample_id}", json={"notes": "x"}, headers=headers)
    assert patch.status_code == 404

    async with session_factory() as session:
        row = (
            await session.execute(select(Sample).where(Sample.sample_code == "S-001"))
        ).scalar_one()
        linked = (await session.execute(select(FastqFile))).scalar_one()
        entries = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == "sample", AuditLog.action == "delete"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert row.deleted_at is not None
    assert str(linked.sample_id) == sample_id
    [entry] = entries
    assert entry.before_state is not None and entry.before_state["sampleCode"] == "S-001"
    assert entry.after_state == {"deletedAt": row.deleted_at.isoformat()}


async def test_bulk_delete_is_soft_and_scoped_to_workspace(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers, other_headers = await _setup(make_user, make_workspace, login)
    first = await _create(client, headers, "S-001")
    second = await _create(client, headers, "S-002")
    foreign = await _create(client, other_headers, "E-001")

    response = await client.request(
        "DELETE",
        "/api/v1/samples/bulk",
        json={"ids": [first, second, foreign]},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == {"deleted": 2}

    # Deleting again counts nothing; the other workspace's sample is untouched.
    repeat = await client.request(
        "DELETE", "/api/v1/samples/bulk", json={"ids": [first]}, headers=headers
    )
    assert repeat.json() == {"deleted": 0}
    assert (
        await client.get(f"/api/v1/samples/{foreign}", headers=other_headers)
    ).status_code == 200

    async with session_factory() as session:
        rows = (await session.execute(select(Sample).order_by(Sample.sample_code))).scalars().all()
        actions = (
            (await session.execute(select(AuditLog.action).where(AuditLog.entity_type == "sample")))
            .scalars()
            .all()
        )
    assert [(r.sample_code, r.deleted_at is not None) for r in rows] == [
        ("E-001", False),
        ("S-001", True),
        ("S-002", True),
    ]
    assert sorted(actions).count("bulk_delete") == 2


async def test_other_workspace_cannot_delete(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
) -> None:
    headers, other_headers = await _setup(make_user, make_workspace, login)
    sample_id = await _create(client, headers, "S-001")

    attempt = await client.delete(f"/api/v1/samples/{sample_id}", headers=other_headers)
    assert attempt.status_code == 404
    assert (await client.get(f"/api/v1/samples/{sample_id}", headers=headers)).status_code == 200


async def test_codes_of_deleted_samples_are_not_reused(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
) -> None:
    headers, _ = await _setup(make_user, make_workspace, login)
    sample_id = await _create(client, headers, "S-001")
    await client.delete(f"/api/v1/samples/{sample_id}", headers=headers)

    recreate = await client.post(
        "/api/v1/samples", json={"sampleCode": "S-001", "modality": "genomics"}, headers=headers
    )
    assert recreate.status_code == 409
    assert "deleted sample" in recreate.json()["detail"]

    imported = await client.post(
        "/api/v1/samples/import",
        files={"file": ("samples.csv", b"sampleCode,modality\nS-001,genomics\n", "text/csv")},
        headers=headers,
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["created"] == 0 and imported.json()["skipped"] == 1


async def test_deleted_sample_cannot_be_used_in_a_run(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
) -> None:
    lead = await make_user("lead@lab.io")
    await make_workspace("lab-west", {lead.id: Role.bioinformatics_lead})
    headers = ws(await login("lead@lab.io"), "lab-west")
    sample_id = await _create(client, headers, "S-001")
    await client.delete(f"/api/v1/samples/{sample_id}", headers=headers)

    run = await client.post(
        "/api/v1/runs", json={"pipelineId": "rnaseq", "sampleIds": [sample_id]}, headers=headers
    )
    assert run.status_code == 422
    assert sample_id in run.json()["detail"]
