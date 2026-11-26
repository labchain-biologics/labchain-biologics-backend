#!/usr/bin/env python3
"""
End-to-end walkthrough of the API through the Python SDK (``sdk/``), in business order.

Prerequisites:
  - API running (``uv run poe start-dev``) with ``BOOTSTRAP_REGISTRATION_ENABLED=true``
  - Postgres + LocalStack up (``uv run poe start-local-run``), migrations applied
  - SDK installed (``uv sync --all-packages --extra dev``)

Usage:
  uv run poe e2e
  uv run poe e2e --base-url http://127.0.0.1:8000
  uv run poe e2e --email lead@example.com --password 'Secret123!'

With ``AWS_BATCH_ENABLED=false`` the run is recorded but not executed: the walkthrough says so
and skips waiting for results instead of pretending they exist.
"""

from __future__ import annotations

import argparse
import functools
import gzip
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import httpx
from titerlane import Client, ExecutionDisabledError, TiterlaneError

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_PIPELINE_ID = "rnaseq"
STREAM_SECONDS = 12.0

T = TypeVar("T")


def step(name: str, action: Callable[[], T]) -> T:
    print(f"\n→ [{name}]")
    result = action()
    print("  ✓")
    return result


def register(base_url: str, email: str, password: str, full_name: str) -> None:
    """Bootstrap registration is development-only, so it is not part of the SDK."""
    response = httpx.post(
        f"{base_url.rstrip('/')}/api/v1/auth/register",
        params={"fullName": full_name},
        json={"email": email, "password": password},
        timeout=30.0,
    )
    if response.status_code == 409:
        print("  (account already exists, continuing with login)")
        return
    if response.status_code != 201:
        raise RuntimeError(
            f"Registration failed ({response.status_code}): {response.text[:300]}. "
            "Is BOOTSTRAP_REGISTRATION_ENABLED=true?"
        )


def fake_fastq(directory: Path, name: str) -> Path:
    path = directory / name
    path.write_bytes(gzip.compress(f"@{name}\nACGTACGT\n+\nIIIIIIII\n".encode() * 200))
    return path


def run_walkthrough(args: argparse.Namespace) -> int:
    email = args.email or f"e2e.lead.{uuid.uuid4().hex[:8]}@example.com"
    workspace = args.workspace or f"e2e-{uuid.uuid4().hex[:8]}"
    sample_code = f"SMP-E2E-{uuid.uuid4().hex[:8].upper()}"

    with httpx.Client() as probe:
        step("0. Health", lambda: probe.get(f"{args.base_url}/health").raise_for_status())
    step("1. Register", lambda: register(args.base_url, email, args.password, args.full_name))

    # A password session is only used to create the workspace and a personal access token.
    with step(
        "2. Login", lambda: Client.login(email, args.password, base_url=args.base_url)
    ) as session:
        me = step("3. Current user", session.auth.me)
        print(f"  {me.email}, member of {[m.slug for m in me.memberships]}")
        if workspace not in {m.slug for m in me.memberships}:
            step("3b. Create workspace", lambda: session.workspaces.create(workspace, workspace))
        token = step(
            "3c. Create personal access token",
            lambda: session.auth.tokens.create("e2e walkthrough", expires_in_days=1),
        )
        print(f"  token {token.token_prefix}…")

    with Client(args.base_url, token=token.token, workspace=workspace) as client:
        sample = step(
            "4. Create sample",
            lambda: client.samples.create(
                sample_code=sample_code,
                patient_id="PAT-E2E-001",
                project_code="PRJ-E2E",
                modality="transcriptomics",
                assay="bulk_rna",
                tissue_type="blood",
                collection_date="2026-08-12",
                rin_din=8.4,
                concentration_ng_ul=125.5,
                volume_ul=50.0,
                qc_notes="E2E walkthrough sample",
                metadata={"source": "e2e_api_walkthrough"},
            ),
        )
        step("5a. List samples", lambda: client.samples.list(limit=10))
        step("5b. Get sample", lambda: client.samples.get(sample.id))
        step(
            "6. Update sample QC → pass",
            lambda: client.samples.update(
                sample.id, qc_status="pass", qc_notes="QC passed during E2E walkthrough"
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            for pair in ("R1", "R2"):
                reads = fake_fastq(Path(tmp), f"{sample_code}_{pair}.fastq.gz")
                fastq = step(
                    f"7. Upload + verify FASTQ {pair}",
                    functools.partial(
                        client.fastq.upload, reads, sample_id=sample.id, read_pair=pair
                    ),
                )
                print(f"  {fastq.verification_status.value}, md5={fastq.computed_md5}")

        pipelines = step("8a. List pipelines", client.pipelines.list)
        pipeline_id = args.pipeline_id
        if pipeline_id not in {p.id for p in pipelines}:
            pipeline_id = pipelines[0].id
            print(f"  requested pipeline unavailable, falling back to {pipeline_id}")
        step("8b. Get pipeline", lambda: client.pipelines.get(pipeline_id))

        run = step(
            "9. Launch pipeline run",
            lambda: client.runs.launch(pipeline_id, sample_ids=[sample.id]),
        )
        print(f"  status={run.status.value}, executionSubmitted={run.execution_submitted}")
        step("10a. List runs", lambda: client.runs.list(limit=10))
        step("10b. Get run", lambda: client.runs.get(run.id))

        print(f"\n→ [11. Stream run logs] (up to {STREAM_SECONDS:.0f} s)")
        deadline = time.monotonic() + STREAM_SECONDS
        for event in client.runs.stream_logs(run.id):
            print(f"  {event.kind}: {event.data[:100]}")
            if time.monotonic() > deadline:
                print("  (stopped following)")
                break

        try:
            run = step(
                "12. Wait for the run",
                lambda: client.runs.wait(run.id, timeout=args.wait_seconds, poll_interval=10),
            )
        except ExecutionDisabledError as exc:
            print(f"  ⚠ {exc}")
        except TiterlaneError as exc:
            print(f"  ⚠ {type(exc).__name__}: {exc}")

        outputs = step("13a. List results for run", lambda: client.results.for_run(run.id))
        step("13b. List results (by runId)", lambda: client.results.list(run_id=run.id))
        if outputs:
            with tempfile.TemporaryDirectory() as tmp:
                path = step(
                    "13c. Download first result (MD5-checked)",
                    lambda: client.results.download(outputs[0].id, tmp),
                )
                print(f"  {path.name}: {path.stat().st_size} bytes")
        else:
            print("\n  ⚠ No result files (run not executed or not finished): download skipped")

        step("14. Revoke token", lambda: client.auth.tokens.revoke(token.id))

    print("\n" + "=" * 60)
    print("E2E walkthrough completed.")
    print(f"  email     = {email}")
    print(f"  workspace = {workspace}")
    print(f"  sampleId  = {sample.id}")
    print(f"  runId     = {run.id} ({run.status.value})")
    print(f"  pipeline  = {pipeline_id}")
    print("=" * 60)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Chronological walkthrough of the Titerlane Biologics API via the Python SDK",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument(
        "--workspace", default=None, help="Workspace slug (default: a new random workspace)"
    )
    parser.add_argument("--email", default=None, help="Account email (default: random)")
    parser.add_argument("--password", default="E2eSecret123!", help="Password (≥ 8 characters)")
    parser.add_argument(
        "--full-name", default="E2E Bioinformatics Lead", help="Display name at registration"
    )
    parser.add_argument(
        "--pipeline-id", default=DEFAULT_PIPELINE_ID, help="nf-core pipeline to launch"
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=60.0,
        help="How long to wait for an executed run to finish",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        raise SystemExit(run_walkthrough(args))
    except Exception as exc:
        print(f"\nE2E walkthrough failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
