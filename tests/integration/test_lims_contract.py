"""LIMS contract: sample fields, unique codes, server-managed status, cross-workspace links."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.audit import AuditLog
from app.models.user import Role, User
from app.models.workspace import Workspace
from tests.integration.conftest import FakeS3

MakeUser = Callable[..., Awaitable[User]]
MakeWorkspace = Callable[..., Awaitable[Workspace]]
Login = Callable[[str], Awaitable[dict[str, str]]]

FULL_SAMPLE = {
    "sampleCode": "SMP-2026-001",
    "modality": "genomics",
    "assay": "exome",
    "sampleType": "tumor",
    "patientId": "PT-01",
    "tissueType": "Tumor",
    "organism": "Homo sapiens",
    "pairedGroup": "PT-01-pair",
    "platform": "Illumina NovaSeq 6000",
    "libraryPrepKit": "Illumina DNA Prep with Exome 2.5 Enrichment",
    "targetPanel": "Exome 2.5 Panel v1.0 - GRCh38",
    "indexId": "UDI-0001",
    "rinDin": 7.8,
    "concentrationNgUl": 42.0,
    "a260280": 1.86,
    "notes": "received on dry ice",
}


async def _lead(
    make_user: MakeUser, make_workspace: MakeWorkspace, login: Login, slug: str = "lab-west"
) -> tuple[User, dict[str, str]]:
    user = await make_user(f"lead@{slug}.io")
    await make_workspace(slug, {user.id: Role.bioinformatics_lead})
    headers = await login(f"lead@{slug}.io")
    return user, {**headers, "X-Titerlane-Workspace": slug}


async def test_sample_round_trips_all_lims_fields(
    client: httpx.AsyncClient, make_user: MakeUser, make_workspace: MakeWorkspace, login: Login
) -> None:
    user, headers = await _lead(make_user, make_workspace, login)

    created = await client.post(
        "/api/v1/samples", json={**FULL_SAMPLE, "status": "completed"}, headers=headers
    )
    assert created.status_code == 201, created.text
    body = created.json()
    for key, value in FULL_SAMPLE.items():
        assert body[key] == value, key
    assert body["status"] == "registered"  # server-managed, client value ignored
    assert body["createdBy"] == str(user.id)

    duplicate = await client.post("/api/v1/samples", json=FULL_SAMPLE, headers=headers)
    assert duplicate.status_code == 409

    filtered = await client.get("/api/v1/samples?assay=exome&status=registered", headers=headers)
    assert [s["sampleCode"] for s in filtered.json()] == ["SMP-2026-001"]


async def test_update_audits_full_snapshot_and_rejects_duplicate_code(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, headers = await _lead(make_user, make_workspace, login)
    first = (await client.post("/api/v1/samples", json=FULL_SAMPLE, headers=headers)).json()
    await client.post(
        "/api/v1/samples", json={"sampleCode": "SMP-2", "modality": "genomics"}, headers=headers
    )

    clash = await client.patch(
        f"/api/v1/samples/{first['id']}", json={"sampleCode": "SMP-2"}, headers=headers
    )
    assert clash.status_code == 409

    ok = await client.patch(
        f"/api/v1/samples/{first['id']}", json={"platform": "NextSeq 2000"}, headers=headers
    )
    assert ok.status_code == 200
    assert ok.json()["libraryPrepKit"] == FULL_SAMPLE["libraryPrepKit"]

    async with session_factory() as session:
        entry = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.entity_id == first["id"], AuditLog.action == "update"
                )
            )
        ).scalar_one()
    assert entry.before_state is not None and entry.after_state is not None
    assert entry.before_state["platform"] == "Illumina NovaSeq 6000"
    assert entry.after_state["platform"] == "NextSeq 2000"
    assert entry.after_state["targetPanel"] == FULL_SAMPLE["targetPanel"]


async def test_csv_import_maps_new_fields_and_skips_duplicates(
    client: httpx.AsyncClient, make_user: MakeUser, make_workspace: MakeWorkspace, login: Login
) -> None:
    _, headers = await _lead(make_user, make_workspace, login)
    await client.post(
        "/api/v1/samples", json={"sampleCode": "S-1", "modality": "genomics"}, headers=headers
    )
    csv_body = (
        "sampleCode,modality,assay,sample_type,platform,a260280\n"
        "S-1,genomics,wgs,tumor,NovaSeq,1.9\n"
        "S-2,genomics,wgs,normal,NovaSeq,2.0\n"
        "S-2,genomics,wgs,normal,NovaSeq,2.0\n"
        "S-3,genomics,WGS,normal,NovaSeq,2.0\n"
    )
    response = await client.post(
        "/api/v1/samples/import",
        files={"file": ("samples.csv", csv_body, "text/csv")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 1
    assert body["skipped"] == 3
    imported = body["samples"][0]
    assert (imported["sampleCode"], imported["sampleType"], imported["a260280"]) == (
        "S-2",
        "normal",
        2.0,
    )


async def test_status_follows_fastq_registration_and_verified_upload(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    fake_s3: FakeS3,
) -> None:
    _, headers = await _lead(make_user, make_workspace, login)
    sample = (await client.post("/api/v1/samples", json=FULL_SAMPLE, headers=headers)).json()
    run = await client.post(
        "/api/v1/sequencing-runs",
        json={"runName": "RUN-01", "flowcellId": "HVKJ2DSX5", "readLength": "2x150"},
        headers=headers,
    )
    assert run.status_code == 201, run.text

    fastq = await client.post(
        "/api/v1/fastq/register",
        json={
            "filename": "SMP-2026-001_R1.fastq.gz",
            "sizeBytes": 1024,
            "sampleId": sample["id"],
            "sequencingRunId": run.json()["id"],
            "readPair": "R1",
        },
        headers=headers,
    )
    assert fastq.status_code == 201, fastq.text
    after_fastq = await client.get(f"/api/v1/samples/{sample['id']}", headers=headers)
    assert after_fastq.json()["status"] == "fastq_received"

    # Verification needs the object to exist in storage.
    not_uploaded = await client.post(f"/api/v1/fastq/{fastq.json()['id']}/verify", headers=headers)
    assert not_uploaded.status_code == 409

    content = b"@r1 ACGT + IIII"
    fake_s3.objects[fastq.json()["s3Key"]] = content
    verified = await client.post(f"/api/v1/fastq/{fastq.json()['id']}/verify", headers=headers)
    assert verified.status_code == 200, verified.text
    assert verified.json()["verificationStatus"] == "verified"
    assert verified.json()["computedMd5"] == hashlib.md5(content).hexdigest()

    listed = await client.get(f"/api/v1/fastq?sampleId={sample['id']}", headers=headers)
    assert [(f["filename"], f["sizeBytes"]) for f in listed.json()] == [
        ("SMP-2026-001_R1.fastq.gz", len(content))
    ]


async def test_fastq_checksum_mismatch_is_reported(
    client: httpx.AsyncClient,
    make_user: MakeUser,
    make_workspace: MakeWorkspace,
    login: Login,
    fake_s3: FakeS3,
) -> None:
    _, headers = await _lead(make_user, make_workspace, login)
    registered = (
        await client.post(
            "/api/v1/fastq/register",
            json={"filename": "x_R1.fastq.gz", "expectedMd5": "0" * 32},
            headers=headers,
        )
    ).json()
    fake_s3.objects[registered["s3Key"]] = b"corrupted"
    response = await client.post(f"/api/v1/fastq/{registered['id']}/verify", headers=headers)
    assert response.json()["verificationStatus"] == "mismatch"


async def test_cannot_link_resources_from_another_workspace(
    client: httpx.AsyncClient, make_user: MakeUser, make_workspace: MakeWorkspace, login: Login
) -> None:
    _, west = await _lead(make_user, make_workspace, login, "lab-west")
    _, east = await _lead(make_user, make_workspace, login, "lab-east")
    foreign_sample = (await client.post("/api/v1/samples", json=FULL_SAMPLE, headers=east)).json()
    foreign_run = (
        await client.post("/api/v1/sequencing-runs", json={"runName": "R"}, headers=east)
    ).json()

    fastq = await client.post(
        "/api/v1/fastq/register",
        json={"filename": "x.fastq.gz", "sampleId": foreign_sample["id"]},
        headers=west,
    )
    assert fastq.status_code == 422
    fastq_run = await client.post(
        "/api/v1/fastq/register",
        json={"filename": "x.fastq.gz", "sequencingRunId": foreign_run["id"]},
        headers=west,
    )
    assert fastq_run.status_code == 422
    launch = await client.post(
        "/api/v1/runs",
        json={"pipelineId": "sarek", "sampleIds": [foreign_sample["id"]]},
        headers=west,
    )
    assert launch.status_code == 422

    untouched = await client.get(f"/api/v1/samples/{foreign_sample['id']}", headers=east)
    assert untouched.json()["status"] == "registered"


async def test_launch_rejects_unknown_pipeline_version(
    client: httpx.AsyncClient, make_user: MakeUser, make_workspace: MakeWorkspace, login: Login
) -> None:
    _, headers = await _lead(make_user, make_workspace, login)
    response = await client.post(
        "/api/v1/runs",
        json={"pipelineId": "rnaseq", "pipelineVersion": "dev; rm -rf /"},
        headers=headers,
    )
    assert response.status_code == 422
