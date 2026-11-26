# Async client

`AsyncClient` is the asyncio version of `Client`, for asynchronous applications (FastAPI or
aiohttp services, Jupyter with a running event loop) and for concurrent transfers. It is
built on `httpx.AsyncClient` and has exactly the same resources, methods and arguments as
`Client`; the SDK's test suite fails if the two drift apart.

The differences:

| `Client` | `AsyncClient` |
| --- | --- |
| `client.samples.get(id)` | `await client.samples.get(id)` |
| `for s in client.samples.iter():` | `async for s in client.samples.iter():` |
| `for e in client.runs.stream_logs(id):` | `async for e in client.runs.stream_logs(id):` |
| `with Client() as client:` | `async with AsyncClient() as client:` |
| `Client.login(...)` | `await AsyncClient.login(...)` |
| `client.close()` | `await client.close()` |
| `transport=httpx.BaseTransport` | `transport=httpx.AsyncBaseTransport` |

Configuration (`TITERLANE_URL`, `TITERLANE_TOKEN`, `TITERLANE_WORKSPACE`), errors, retries and
secrets handling are the same as for `Client`.

## Example: upload a whole run concurrently

```python
import asyncio
from pathlib import Path

from titerlane import AsyncClient


async def main() -> None:
    async with AsyncClient() as client:
        sample = await client.samples.create(sample_code="RNA-001", modality="transcriptomics")
        files = sorted(Path("fastq/").glob("RNA-001_*.fastq.gz"))
        uploaded = await asyncio.gather(
            *(client.fastq.upload(path, sample_id=sample.id) for path in files)
        )
        print([f.verification_status for f in uploaded])

        run = await client.runs.launch("rnaseq", sample_ids=[sample.id])
        async for event in client.runs.stream_logs(run.id):
            if event.kind == "log":
                print(event.data)


asyncio.run(main())
```

Limit concurrency yourself (for example with `asyncio.Semaphore`) when uploading many large
files, so you do not saturate your network link.

## Event loop friendliness

The async client never blocks the event loop on disk work: computing a FASTQ's MD5, reading
the file for upload, reading a CSV for import and writing a downloaded result all run in a
worker thread (`asyncio.to_thread`).

## In Jupyter

Notebooks already run an event loop, so use top-level `await` instead of `asyncio.run`:

```python
from titerlane import AsyncClient

client = AsyncClient()
samples = [s async for s in client.samples.iter(qc_status="pass")]
await client.close()
```
