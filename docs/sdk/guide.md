# User guide

This page follows a sample from registration to results. Examples assume a configured client
(see [Configure](index.md#configure)):

```python
from titerlane import Client

client = Client()
```

The SDK uses Python names (`sample_code`, `qc_status`); the API's camelCase JSON is handled
for you. Enum arguments accept the enum (`QcStatus.pass_`) or its string value (`"pass"`).
Models and enums live in `titerlane.models`.

## Samples

Lab technicians and bioinformatics leads can manage samples.

```python
sample = client.samples.create(
    sample_code="WGS-042",
    modality="genomics",
    assay="wgs",
    sample_type="tumor",
    organism="Homo sapiens",
    concentration_ng_ul=48.5,
    metadata={"cohort": "pilot"},
)

client.samples.update(sample.id, qc_status="pass", qc_notes="DIN 7.9")
```

You can also pass a model instead of keyword arguments:

```python
from titerlane.models import SampleCreate

client.samples.create(SampleCreate(sample_code="WGS-043", modality="genomics"))
```

### Listing and pagination

`list` returns one page (`limit`, `offset`); `iter` walks every page for you.

```python
first_page = client.samples.list(status="fastq_received", limit=20)

for sample in client.samples.iter(modality="transcriptomics", qc_status="pass"):
    print(sample.sample_code, sample.status)
```

Filters: `modality`, `assay`, `status`, `qc_status`.

### Bulk operations and CSV import

```python
client.samples.bulk_update({
    sample_a.id: {"qc_status": "pass"},
    sample_b.id: {"qc_status": "fail", "qc_notes": "low yield"},
})

deleted = client.samples.bulk_delete([sample_c.id, sample_d.id])  # returns the count

result = client.samples.import_csv("samples.csv")
print(result.created, result.skipped, result.errors)
```

The CSV is UTF-8 with one column per sample field (`sampleCode` or `sample_code`, ...).
Existing or duplicated sample codes are skipped and reported in `errors`; see
[POST /samples/import](../api/samples/import.md).

Deleting a sample is a soft delete: it disappears from listings, but its history stays in the
audit trail.

## Sequencing runs

```python
seq_run = client.sequencing_runs.create(
    run_name="NovaSeq-2026-11-25", instrument="NovaSeq X", flowcell_id="22FCXYZ", read_length="2x150"
)
```

## FASTQ files

`fastq.upload` does the whole transfer in one call:

1. computes the file's MD5 locally;
2. registers the file and gets a signed upload URL;
3. uploads the file to object storage;
4. asks the server to compute the MD5 of the stored object and compare.

```python
fastq = client.fastq.upload(
    "WGS-042_R1.fastq.gz",
    sample_id=sample.id,
    sequencing_run_id=seq_run.id,
    read_pair="R1",
    expected_md5="9e107d9d372bb6826bd81d3542a419d6",  # optional, e.g. from the provider manifest
)
print(fastq.verification_status)  # verified
```

- With `expected_md5`, a local file that does not match raises `ChecksumMismatchError`
  **before** anything is uploaded.
- If the stored object does not match, `upload` raises `ChecksumMismatchError`. The FASTQ
  record stays in the workspace with status `mismatch`, so the failed transfer is traceable.
- The upload URL is signed for `Content-Type: application/gzip`, so send gzipped FASTQ
  (`.fastq.gz`).

For a custom transfer (another upload tool, an object already in the bucket), use the steps
separately:

```python
registration = client.fastq.register(filename="WGS-042_R2.fastq.gz", size_bytes=size,
                                     expected_md5=md5, sample_id=sample.id, read_pair="R2")
# PUT the file to registration.upload_url with Content-Type: application/gzip, then:
verification = client.fastq.verify(registration.id)
```

`registration.upload_url` is a credential until it expires: do not log it.

List files with `client.fastq.list(sample_id=...)` or `client.fastq.iter(...)`.

## Pipelines

```python
for pipeline in client.pipelines.list():
    print(pipeline.id, pipeline.version, pipeline.versions, pipeline.assays)

rnaseq = client.pipelines.get("rnaseq")
print(rnaseq.default_params)
```

## Launching a run

Launching requires the `bioinformatics_lead` role, and every selected sample needs verified
FASTQ files.

```python
run = client.runs.launch(
    "rnaseq",
    sample_ids=[sample.id],
    pipeline_version="3.14.0",          # default "latest"
    parameters={"aligner": "star_salmon"},
)
print(run.status, run.execution_submitted)
```

!!! warning "Execution may be disabled"
    When pipeline execution is disabled on the server (`AWS_BATCH_ENABLED=false`), the run is
    recorded but never submitted: `run.execution_submitted` is `False` and the run stays
    `pending`. Its log says so. The SDK does not pretend otherwise: `runs.wait` raises
    `ExecutionDisabledError` instead of waiting forever.

## Following a run

### Wait for the end

```python
from titerlane import RunFailedError, RunTimeoutError

try:
    run = client.runs.wait(run.id, timeout=6 * 3600, poll_interval=30)
except RunFailedError as exc:
    print("failed:", exc.status, exc)
except RunTimeoutError:
    print("still running on the server")
```

`wait` polls `GET /runs/{id}`. Pass `raise_on_failure=False` to get the failed or cancelled
run back instead of an exception.

### Stream the logs live

`stream_logs` follows the server-sent event stream until the run ends:

```python
for event in client.runs.stream_logs(run.id):
    if event.kind == "log":
        print(event.index, event.data)
    elif event.kind == "status":
        print("status ->", event.data)
    elif event.kind == "end":
        print("finished:", event.data)
```

The server closes the stream when the run finishes, if it was never submitted, or after an
hour. To resume, read the lines you missed with `logs`:

```python
lines = client.runs.logs(run.id, after=last_index)  # lines with index > last_index
```

See [Logs & Nextflow events](../api/runs/events.md) for where log lines come from.

### List runs

```python
for r in client.runs.iter(status="running"):
    print(r.id, r.pipeline_id, r.progress)
```

## Results

```python
outputs = client.results.for_run(run.id)       # read from the run's output directory
vcfs = client.results.list(file_type="vcf")    # every recorded output in the workspace

for output in outputs:
    path = client.results.download(output.id, "results/")
    print(path)
```

`download` saves to a file path, or into an existing directory under the file's own name. It
writes to a temporary file first and checks the MD5 when the server knows it: on a mismatch
it raises `ChecksumMismatchError` and leaves nothing at the destination.

`client.results.download_url(output.id)` returns a short-lived signed URL if you want to hand
the transfer to another tool. Treat it as a secret until it expires.

## A complete script

The repository's end-to-end walkthrough, `scripts/e2e_api_walkthrough.py`
(`uv run poe e2e`), drives every step above against a running server with the SDK. It is a
good starting point for your own automation.
