# LabChain Biologics Python SDK

Python client for the [LabChain Biologics](https://github.com/labchain-biologics/labchain-biologics-backend)
API: a multi-omics LIMS with nf-core / Nextflow orchestration and a 21 CFR Part 11 audit trail.
Register samples, upload and verify FASTQ files, launch pipelines, follow their logs and
download results from scripts, notebooks or CI.

The SDK is licensed under **Apache-2.0**. The server is AGPL-3.0-only; the SDK does not
include server code.

> Status: alpha (0.x). The API may change between minor versions.

## Install

```bash
pip install labchain-biologics-sdk
```

Requires Python 3.11+.

## Authenticate

Create a personal access token once, signed in with your password (tokens cannot create
tokens):

```python
from labchain import Client

with Client.login("you@lab.example", "your-password", base_url="https://lims.example") as c:
    created = c.auth.tokens.create("analysis notebook", expires_in_days=90)
    print(created.token)  # shown only now: store it in a secret manager
```

Then configure the client through the environment:

```bash
export LABCHAIN_URL=https://lims.example
export LABCHAIN_TOKEN=lcb_pat_...
export LABCHAIN_WORKSPACE=helix-genomics   # workspace slug
```

The token acts as you, with your role in each workspace. The server enforces permissions.

## Example: from samples to results

```python
from labchain import Client

with Client() as client:
    sample = client.samples.create(
        sample_code="RNA-001", modality="transcriptomics", assay="bulk_rna"
    )

    # Computes the MD5 locally, uploads to object storage, and has the server verify it.
    client.fastq.upload("RNA-001_R1.fastq.gz", sample_id=sample.id, read_pair="R1")
    client.fastq.upload("RNA-001_R2.fastq.gz", sample_id=sample.id, read_pair="R2")

    run = client.runs.launch("rnaseq", sample_ids=[sample.id])  # bioinformatics_lead only
    for event in client.runs.stream_logs(run.id):
        if event.kind == "log":
            print(event.data)

    run = client.runs.wait(run.id)
    for output in client.results.for_run(run.id):
        client.results.download(output.id, "results/")  # MD5-checked
```

If pipeline execution is disabled on the server, `launch` still records the run but
`run.execution_submitted` is `False`, and `wait` raises `ExecutionDisabledError` instead of
waiting forever.

## Workspaces

Workspace-scoped calls use `LABCHAIN_WORKSPACE` or the `workspace=` argument. Switch without
reconnecting:

```python
east = client.with_workspace("lab-east")
east.samples.list(limit=10)
```

## Errors

Every error derives from `labchain.LabChainError`. API errors carry `status_code` and the
server's `detail`:

| Exception | When |
| --- | --- |
| `AuthenticationError` | 401: missing, expired or revoked credentials |
| `PermissionDeniedError` | 403: your role does not allow the action |
| `NotFoundError` | 404: unknown resource, or a workspace you do not belong to |
| `ConflictError` | 409: duplicate or already in that state |
| `UnprocessableError` | 422: invalid content |
| `ServerError` | 5xx |
| `APIConnectionError` | network failure, or object storage refused a transfer |
| `ChecksumMismatchError` | a transferred file does not match its MD5 |
| `ExecutionDisabledError`, `RunFailedError`, `RunTimeoutError` | from `runs.wait` |

Idempotent requests (GET) are retried twice on 502/503/504 and network errors.

Credentials and signed storage URLs are never logged nor included in `repr()` or error
messages.

## Development

The SDK lives in the backend repository so API and client change together:

```bash
uv sync --all-packages --extra dev
uv run poe sdk-test        # unit + contract tests (SDK vs openapi.json)
uv run poe test            # includes tests/integration/test_sdk.py (SDK against the real app)
uv run poe sdk-typecheck
```
