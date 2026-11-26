# GET /api/v1/runs

List pipeline jobs for the current workspace.

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `200 OK` |

## Request model

No body.

### Query

| Param | Type | Default | Description |
| --- | --- | --- | --- |
| `status` | `JobStatus?` | — | Filter by status |
| `limit` | `int` | `50` | 1–200 |
| `offset` | `int` | `0` | Pagination offset |

## Response model (`PipelineJobRead[]`)

See [POST /runs](launch.md).

## Example

```bash
curl -s 'http://localhost:8000/api/v1/runs?status=running&limit=10' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-Titerlane-Workspace: demo'
```

```json
[
  {
    "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    "workspace": "demo",
    "pipelineId": "rnaseq",
    "pipelineName": "nf-core/rnaseq",
    "pipelineVersion": "3.14.0",
    "status": "running",
    "sequencingRunId": null,
    "sampleIds": ["11111111-1111-1111-1111-111111111111"],
    "parameters": { "aligner": "star_salmon" },
    "awsBatchJobId": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
    "executionSubmitted": true,
    "nextflowRunName": "RNA-001-rnaseq",
    "workDir": "s3://titerlane-biologics/demo/work/...",
    "launchedBy": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "createdAt": "2026-08-10T12:00:00Z",
    "updatedAt": "2026-08-10T12:00:00Z",
    "startedAt": "2026-08-10T12:00:00Z",
    "finishedAt": null,
    "outputFiles": []
  }
]
```
