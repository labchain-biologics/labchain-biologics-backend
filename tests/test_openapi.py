"""Unit tests for the public OpenAPI contract."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.main import app
from app.models.pipeline import JobStatus
from app.schemas.pipeline import PipelineJobRead

OPERATION_ID = re.compile(r"^[a-z][a-z0-9_]*$")


def _operations() -> list[dict[str, Any]]:
    schema = app.openapi()
    return [operation for path in schema["paths"].values() for operation in path.values()]


def test_operation_ids_are_unique_readable_names() -> None:
    operation_ids = [operation["operationId"] for operation in _operations()]

    assert len(operation_ids) == len(set(operation_ids)), "duplicate operationId"
    for operation_id in operation_ids:
        assert OPERATION_ID.match(operation_id), operation_id
        # FastAPI's default ids append the path and method (``list_samples_api_v1_samples_get``).
        assert "_api_v1_" not in operation_id, operation_id


def test_operation_ids_for_core_routes() -> None:
    paths = app.openapi()["paths"]
    assert paths["/api/v1/samples"]["get"]["operationId"] == "list_samples"
    assert paths["/api/v1/runs"]["post"]["operationId"] == "launch_run"
    assert paths["/health"]["get"]["operationId"] == "health"


def test_run_schema_exposes_execution_submitted() -> None:
    run_schema = app.openapi()["components"]["schemas"]["PipelineJobRead"]
    assert "executionSubmitted" in run_schema["properties"]
    assert "executionSubmitted" in run_schema["required"]


def _run(**overrides: Any) -> PipelineJobRead:
    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "workspace": "lab-west",
        "pipeline_id": "rnaseq",
        "pipeline_name": "nf-core/rnaseq",
        "pipeline_version": "3.14.0",
        "status": JobStatus.pending,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return PipelineJobRead(**values)


@pytest.mark.parametrize(("batch_job_id", "submitted"), [(None, False), ("job-123", True)])
def test_execution_submitted_follows_batch_submission(
    batch_job_id: str | None, submitted: bool
) -> None:
    body = _run(aws_batch_job_id=batch_job_id).model_dump(by_alias=True)
    assert body["executionSubmitted"] is submitted
