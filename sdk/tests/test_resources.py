"""Resource methods: request shapes and response parsing."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fakes import NOW, FakeServer, body_of, ok, sample_json

from labchain import Client
from labchain.models import QcStatus, Role, SampleUpdate


def test_create_sample_sends_camel_case(client: Client, server: FakeServer) -> None:
    server.on("POST", "/api/v1/samples", ok(sample_json(rinDin=8.5), 201))
    sample = client.samples.create(sample_code="S-001", modality="genomics", rin_din=8.5)

    sent = body_of(server.last("POST", "/api/v1/samples"))
    assert sent["sampleCode"] == "S-001" and sent["rinDin"] == 8.5
    assert sample.rin_din == 8.5 and sample.sample_code == "S-001"


def test_create_rejects_unknown_field_locally(client: Client, server: FakeServer) -> None:
    with pytest.raises(ValueError, match="sample_cod"):
        client.samples.create(sample_cod="typo", modality="genomics")
    assert server.requests == []


def test_create_rejects_model_and_fields_together(client: Client) -> None:
    from labchain.models import SampleCreate

    with pytest.raises(TypeError):
        client.samples.create(SampleCreate(sample_code="S", modality="genomics"), notes="x")


def test_update_sends_only_changed_fields(client: Client, server: FakeServer) -> None:
    sample_id = str(uuid.uuid4())
    server.on("PATCH", f"/api/v1/samples/{sample_id}", ok(sample_json(qcStatus="pass")))
    sample = client.samples.update(sample_id, qc_status="pass", notes=None)

    assert body_of(server.last("PATCH", f"/api/v1/samples/{sample_id}")) == {
        "qcStatus": "pass",
        "notes": None,
    }
    assert sample.qc_status is QcStatus.pass_


def test_bulk_update_and_delete(client: Client, server: FakeServer) -> None:
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    server.on("PATCH", "/api/v1/samples/bulk", ok([sample_json(), sample_json()]))
    server.on("DELETE", "/api/v1/samples/bulk", ok({"deleted": 2}))

    client.samples.bulk_update({first: {"qc_status": "fail"}, second: SampleUpdate(notes="n")})
    assert body_of(server.last("PATCH", "/api/v1/samples/bulk")) == {
        "items": [
            {"id": first, "patch": {"qcStatus": "fail"}},
            {"id": second, "patch": {"notes": "n"}},
        ]
    }
    assert client.samples.bulk_delete([first, second]) == 2
    assert body_of(server.last("DELETE", "/api/v1/samples/bulk")) == {"ids": [first, second]}


def test_list_filters_skip_unset_values(client: Client, server: FakeServer) -> None:
    server.on("GET", "/api/v1/samples", ok([]))
    client.samples.list(status="fastq_received", qc_status=QcStatus.pass_)
    params = dict(server.last("GET", "/api/v1/samples").url.params)
    assert params == {"status": "fastq_received", "qcStatus": "pass", "limit": "100", "offset": "0"}


def test_iter_walks_all_pages(client: Client, server: FakeServer) -> None:
    server.on(
        "GET",
        "/api/v1/samples",
        ok([sample_json(), sample_json()]),
        ok([sample_json(), sample_json()]),
        ok([sample_json()]),
    )
    assert len(list(client.samples.iter(page_size=2))) == 5
    offsets = [r.url.params["offset"] for r in server.requests]
    assert offsets == ["0", "2", "4"]


def test_import_csv_uploads_multipart(client: Client, server: FakeServer, tmp_path: Path) -> None:
    csv_path = tmp_path / "samples.csv"
    csv_path.write_text("sampleCode,modality\nS-1,genomics\n", encoding="utf-8")
    result_body = {"created": 1, "skipped": 0, "errors": [], "samples": [sample_json()]}
    server.on("POST", "/api/v1/samples/import", ok(result_body))

    result = client.samples.import_csv(csv_path)

    request = server.last("POST", "/api/v1/samples/import")
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    assert b'filename="samples.csv"' in request.content
    assert b"S-1,genomics" in request.content
    assert result.created == 1


def test_members_and_workspaces(client: Client, server: FakeServer) -> None:
    user_id = str(uuid.uuid4())
    member = {
        "userId": user_id,
        "email": "tech@lab.example",
        "fullName": "Tech",
        "role": "lab_technician",
        "isActive": True,
        "joinedAt": NOW,
    }
    server.on("POST", "/api/v1/members", ok(member, 201))
    server.on("PATCH", f"/api/v1/members/{user_id}", ok({**member, "role": "bioinformatics_lead"}))
    server.on("DELETE", f"/api/v1/members/{user_id}", ok(None, 204))
    server.on(
        "POST",
        "/api/v1/workspaces",
        ok(
            {
                "id": str(uuid.uuid4()),
                "slug": "helix",
                "name": "Helix",
                "role": "bioinformatics_lead",
                "createdAt": NOW,
            },
            201,
        ),
    )

    assert client.members.add("tech@lab.example").role is Role.lab_technician
    assert (
        client.members.change_role(user_id, "bioinformatics_lead").role is Role.bioinformatics_lead
    )
    client.members.remove(user_id)
    assert client.workspaces.create("helix", "Helix").slug == "helix"
    assert body_of(server.last("POST", "/api/v1/members")) == {
        "email": "tech@lab.example",
        "role": "lab_technician",
    }


def test_tokens(client: Client, server: FakeServer) -> None:
    token_id = str(uuid.uuid4())
    token = {
        "id": token_id,
        "name": "ci",
        "tokenPrefix": "lcb_pat_abcdefgh",
        "createdAt": NOW,
        "expiresAt": NOW,
        "lastUsedAt": None,
        "revokedAt": None,
    }
    server.on("POST", "/api/v1/auth/tokens", ok({**token, "token": "lcb_pat_secret"}, 201))
    server.on("DELETE", f"/api/v1/auth/tokens/{token_id}", ok({**token, "revokedAt": NOW}))

    created = client.auth.tokens.create("ci", expires_in_days=30)
    assert created.token == "lcb_pat_secret"
    assert "lcb_pat_secret" not in repr(created)
    assert body_of(server.last("POST", "/api/v1/auth/tokens")) == {
        "name": "ci",
        "expiresInDays": 30,
    }
    assert client.auth.tokens.revoke(token_id).revoked_at is not None


def test_responses_tolerate_new_server_fields(client: Client, server: FakeServer) -> None:
    server.on("GET", "/api/v1/samples", ok([sample_json(newServerField="x")]))
    assert client.samples.list()[0].sample_code == "S-001"
