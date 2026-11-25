"""A scripted fake server on ``httpx.MockTransport`` and JSON builders: no network."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

BASE_URL = "http://lims.test"
TOKEN = "lcb_pat_unit-test-token"
WORKSPACE = "lab-west"
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC).isoformat()

Handler = Callable[[httpx.Request], httpx.Response]


@dataclass
class FakeServer:
    routes: dict[tuple[str, str], list[Handler]] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def on(self, method: str, url_path: str, *responses: Handler | httpx.Response) -> None:
        """Queue responses for ``method url_path``; the last one repeats."""
        handlers = [
            (lambda _r, resp=resp: resp) if isinstance(resp, httpx.Response) else resp
            for resp in responses
        ]
        self.routes[(method, url_path)] = handlers

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        key = (request.method, request.url.path)
        handlers = self.routes.get(key)
        if not handlers:
            return httpx.Response(599, json={"detail": f"unexpected {key}"})
        handler = handlers.pop(0) if len(handlers) > 1 else handlers[0]
        return handler(request)

    def last(self, method: str, url_path: str) -> httpx.Request:
        matches = [r for r in self.requests if (r.method, r.url.path) == (method, url_path)]
        assert matches, f"no {method} {url_path} request"
        return matches[-1]


def ok(body: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body)


def body_of(request: httpx.Request) -> Any:
    return json.loads(request.content)


def sample_json(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "workspace": WORKSPACE,
        "sampleCode": "S-001",
        "modality": "genomics",
        "status": "registered",
        "qcStatus": "pending",
        "metadata": {},
        "createdAt": NOW,
        "updatedAt": NOW,
    }
    data.update(overrides)
    return data


def run_json(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "workspace": WORKSPACE,
        "pipelineId": "rnaseq",
        "pipelineName": "nf-core/rnaseq",
        "pipelineVersion": "3.14.0",
        "status": "submitted",
        "executionSubmitted": True,
        "awsBatchJobId": "job-1",
        "progress": {},
        "createdAt": NOW,
        "updatedAt": NOW,
    }
    data.update(overrides)
    return data
