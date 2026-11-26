# Python SDK

`labchain-biologics-sdk` is the Python client for the LabChain Biologics API. Use it from
scripts, Jupyter notebooks or CI jobs to register samples, upload and verify FASTQ files,
launch nf-core pipelines, follow their logs and download results, without writing HTTP calls
by hand.

| | |
| --- | --- |
| Import name | `labchain` |
| Distribution | `labchain-biologics-sdk` |
| Python | 3.11+ |
| Dependencies | `httpx`, `pydantic` (v2) |
| Licence | Apache-2.0 (the server is AGPL-3.0-only; the SDK contains no server code) |
| Status | Alpha (0.x): the interface may change between minor versions |

The SDK only uses the public API documented in the [API section](../api-overview.md). Anything
it does, you can do with `curl`; the SDK adds typed models, pagination, MD5 checks, retries
and log streaming.

## Install

!!! note "Not on PyPI yet"
    The package is not published yet. Install it from a checkout of this repository.

```bash
git clone https://github.com/labchain-biologics/labchain-biologics-backend.git
pip install ./labchain-biologics-backend/sdk
```

Or, with uv, inside the backend checkout (the SDK is a workspace member):

```bash
uv sync --all-packages
```

## Configure

The client reads three environment variables. Arguments passed to `Client(...)` take
precedence.

| Variable | `Client` argument | Description |
| --- | --- | --- |
| `LABCHAIN_URL` | `base_url` | Server root, without `/api/v1` (e.g. `http://localhost:8000`) |
| `LABCHAIN_TOKEN` | `token` | A [personal access token](authentication.md) (`lcb_pat_...`) |
| `LABCHAIN_WORKSPACE` | `workspace` | Slug of the workspace used by workspace-scoped calls |

```bash
export LABCHAIN_URL=http://localhost:8000
export LABCHAIN_TOKEN=lcb_pat_...
export LABCHAIN_WORKSPACE=demo-lab
```

```python
from labchain import Client

with Client() as client:
    print(client.health())
    me = client.auth.me()
    print(me.email, [(m.slug, m.role) for m in me.memberships])
```

Other `Client` arguments:

| Argument | Default | Description |
| --- | --- | --- |
| `timeout` | `30.0` | Seconds per request (log streams have no read timeout) |
| `max_retries` | `2` | Retries of GET requests on 502/503/504 and network errors |
| `transport` | `None` | A custom `httpx` transport (proxies, tests with `httpx.MockTransport`) |

Use the client as a context manager, or call `client.close()` when done.

## Ten-line tour

```python
from labchain import Client

with Client() as client:
    sample = client.samples.create(sample_code="RNA-001", modality="transcriptomics")
    client.fastq.upload("RNA-001_R1.fastq.gz", sample_id=sample.id, read_pair="R1")
    client.fastq.upload("RNA-001_R2.fastq.gz", sample_id=sample.id, read_pair="R2")
    run = client.runs.launch("rnaseq", sample_ids=[sample.id])
    run = client.runs.wait(run.id)
    for output in client.results.for_run(run.id):
        client.results.download(output.id, "results/")
```

The [user guide](guide.md) walks through each step, and the [reference](reference.md) lists
every method.

## Pages

- [Authentication](authentication.md): personal access tokens, password login, workspaces
- [User guide](guide.md): samples, FASTQ, pipeline runs, logs, results
- [Reference](reference.md): client, resources, models and enums
- [Errors](errors.md): exception hierarchy and retries
