"""
The SDK against the server's public contract (``openapi.json`` at the repository root).

Fails when the API gains, loses or renames a field, enum value or operation that the SDK does
not follow, so contract changes cannot ship without the SDK. Skipped when the SDK is tested
outside the repository.
"""

from __future__ import annotations

import enum
import json
from functools import cache
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from titerlane import Client, models

OPENAPI = Path(__file__).resolve().parents[2] / "openapi.json"

pytestmark = pytest.mark.skipif(not OPENAPI.exists(), reason="openapi.json not available")

# SDK model -> server schema. The SDK uses shorter names for responses.
MODELS: dict[type[BaseModel], str] = {
    models.Token: "Token",
    models.User: "UserMe",
    models.MembershipSummary: "MembershipSummary",
    models.ApiToken: "ApiTokenRead",
    models.ApiTokenCreated: "ApiTokenCreated",
    models.ApiTokenCreate: "ApiTokenCreate",
    models.Workspace: "WorkspaceRead",
    models.WorkspaceCreate: "WorkspaceCreate",
    models.Member: "MemberRead",
    models.MemberCreate: "MemberCreate",
    models.MemberUpdate: "MemberUpdate",
    models.Sample: "SampleRead",
    models.SampleCreate: "SampleCreate",
    models.SampleUpdate: "SampleUpdate",
    models.SampleImportResult: "SampleImportResult",
    models.SequencingRun: "SequencingRunRead",
    models.SequencingRunCreate: "SequencingRunCreate",
    models.FastqFile: "FastqRead",
    models.FastqRegisterRequest: "FastqRegisterRequest",
    models.FastqRegistration: "FastqRegisterResponse",
    models.FastqVerification: "FastqVerifyResponse",
    models.Pipeline: "PipelineCatalogItem",
    models.Run: "PipelineJobRead",
    models.RunCreate: "RunCreateRequest",
    models.RunLogLine: "RunLogLine",
    models.ResultFile: "RunOutputFileRead",
    models.ResultDownload: "ResultDownloadResponse",
}

# Server schemas the SDK deliberately has no model for, and why.
UNMODELLED_SCHEMAS = {
    "HTTPValidationError": "error body, surfaced as UnprocessableError.detail",
    "ValidationError": "item of HTTPValidationError",
    "LoginRequest": "sent by Client.login as a plain body",
    "LogoutResponse": "auth.logout returns None",
    "UserRead": "only returned by bootstrap registration (development only)",
    "WeblogEvent": "posted by Nextflow, not by API clients",
    "Body_import_samples_csv": "multipart form built by samples.import_csv",
    "SampleBulkPatchRequest": "built by samples.bulk_update",
    "SampleBulkPatchItem": "built by samples.bulk_update",
    "SampleBulkDeleteRequest": "built by samples.bulk_delete",
}

ENUMS: dict[type[enum.Enum], str] = {
    models.Role: "Role",
    models.OmicsModality: "OmicsModality",
    models.SampleAssay: "SampleAssay",
    models.SampleType: "SampleType",
    models.SampleStatus: "SampleStatus",
    models.QcStatus: "QcStatus",
    models.JobStatus: "JobStatus",
    models.OutputFileType: "OutputFileType",
    models.FastqVerificationStatus: "FastqVerificationStatus",
}

# operationId -> the SDK entry point that calls it.
OPERATIONS: dict[str, str] = {
    "health": "health",
    "login": "Client.login",
    "logout": "auth.logout",
    "read_me": "auth.me",
    "list_api_tokens": "auth.tokens.list",
    "create_api_token": "auth.tokens.create",
    "revoke_api_token": "auth.tokens.revoke",
    "list_my_workspaces": "workspaces.list",
    "create_workspace": "workspaces.create",
    "list_members": "members.list",
    "add_member": "members.add",
    "change_member_role": "members.change_role",
    "remove_member": "members.remove",
    "list_samples": "samples.list",
    "create_sample": "samples.create",
    "get_sample": "samples.get",
    "update_sample": "samples.update",
    "delete_sample": "samples.delete",
    "bulk_patch_samples": "samples.bulk_update",
    "bulk_delete_samples": "samples.bulk_delete",
    "import_samples_csv": "samples.import_csv",
    "list_sequencing_runs": "sequencing_runs.list",
    "create_sequencing_run": "sequencing_runs.create",
    "get_sequencing_run": "sequencing_runs.get",
    "list_fastq": "fastq.list",
    "get_fastq": "fastq.get",
    "register_fastq": "fastq.register",
    "verify_fastq": "fastq.verify",
    "get_pipelines": "pipelines.list",
    "get_pipeline_by_id": "pipelines.get",
    "list_runs": "runs.list",
    "launch_run": "runs.launch",
    "get_run": "runs.get",
    "get_run_logs": "runs.logs",
    "stream_run_logs": "runs.stream_logs",
    "list_results": "results.list",
    "list_results_for_run": "results.for_run",
    "get_presigned_download": "results.download_url",
}

UNCOVERED_OPERATIONS = {
    "register_bootstrap_user": "development-only bootstrap, disabled in production",
    "receive_weblog_event": "Nextflow callback authenticated by a per-run secret",
}


@cache
def _spec() -> dict[str, Any]:
    return dict(json.loads(OPENAPI.read_text(encoding="utf-8")))


def _schema(name: str) -> dict[str, Any]:
    return dict(_spec()["components"]["schemas"][name])


def _aliases(model: type[BaseModel]) -> dict[str, bool]:
    """camelCase field name -> required, as the SDK sends or expects it."""
    return {(info.alias or name): info.is_required() for name, info in model.model_fields.items()}


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_model_fields_match_schema(model: type[BaseModel]) -> None:
    schema = _schema(MODELS[model])
    server_fields = set(schema.get("properties", {}))
    sdk_fields = _aliases(model)

    assert set(sdk_fields) == server_fields, (
        f"{model.__name__} vs {MODELS[model]}: "
        f"missing in SDK {sorted(server_fields - set(sdk_fields))}, "
        f"unknown to server {sorted(set(sdk_fields) - server_fields)}"
    )
    required = set(schema.get("required", []))
    sdk_required = {name for name, is_required in sdk_fields.items() if is_required}
    if issubclass(model, models.RequestModel):
        # A request must be valid exactly when the server would accept it.
        assert sdk_required == required, f"{model.__name__} required fields differ"
    else:
        # A response may not demand a field the server is allowed to omit.
        assert sdk_required <= required, f"{model.__name__} requires optional fields"


@pytest.mark.parametrize("enum_cls", ENUMS, ids=lambda e: e.__name__)
def test_enum_values_match_schema(enum_cls: type[enum.Enum]) -> None:
    server = set(_schema(ENUMS[enum_cls])["enum"])
    assert {member.value for member in enum_cls} == server


def test_every_server_schema_is_modelled_or_explained() -> None:
    modelled = set(MODELS.values()) | set(ENUMS.values()) | set(UNMODELLED_SCHEMAS)
    unexplained = set(_spec()["components"]["schemas"]) - modelled
    assert not unexplained, f"New server schemas without an SDK model: {sorted(unexplained)}"
    stale = set(UNMODELLED_SCHEMAS) - set(_spec()["components"]["schemas"])
    assert not stale, f"UNMODELLED_SCHEMAS lists schemas the server removed: {sorted(stale)}"


def test_every_operation_has_an_sdk_entry_point() -> None:
    server = {
        operation["operationId"]
        for path in _spec()["paths"].values()
        for operation in path.values()
    }
    covered = set(OPERATIONS) | set(UNCOVERED_OPERATIONS)
    assert server - covered == set(), f"Operations missing from the SDK: {sorted(server - covered)}"
    assert covered - server == set(), f"SDK maps removed operations: {sorted(covered - server)}"


def test_entry_points_exist() -> None:
    client = Client(
        "http://contract.test",
        token="x",
        transport=httpx.MockTransport(lambda r: httpx.Response(500)),
    )
    for operation_id, dotted in OPERATIONS.items():
        target: Any = Client if dotted.startswith("Client.") else client
        for part in dotted.removeprefix("Client.").split("."):
            target = getattr(target, part, None)
            assert target is not None, f"{operation_id}: {dotted} does not exist"
        assert callable(target), f"{operation_id}: {dotted} is not callable"
    client.close()
