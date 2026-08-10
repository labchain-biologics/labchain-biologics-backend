# GET /api/v1/runs/{run_id}

Fetch a single pipeline job including output file metadata.

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `200 OK` |

## Request model

### Path

| Param | Type | Required |
| --- | --- | --- |
| `run_id` | `uuid` | yes |

No body.

## Response model (`PipelineJobRead`)

See [POST /runs](launch.md).

## Example

```bash
curl -s 'http://localhost:8000/api/v1/runs/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-LabChain-Workspace: demo'
```

```json
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
  "awsBatchJobId": "sim-job-123",
  "nextflowRunName": "RNA-001-rnaseq",
  "workDir": "s3://labchain-biologics/demo/work/...",
  "launchedBy": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "createdAt": "2026-08-10T12:00:00Z",
  "updatedAt": "2026-08-10T12:00:00Z",
  "startedAt": "2026-08-10T12:00:00Z",
  "finishedAt": null,
  "outputFiles": [
    {
      "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
      "fileType": "multiqc",
      "filename": "multiqc_report.html",
      "s3Key": "demo/results/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/multiqc_report.html",
      "sizeBytes": 0,
      "md5": null,
      "sampleId": null,
      "metadata": { "format": "html" },
      "downloadUrl": null,
      "createdAt": "2026-08-10T12:00:00Z"
    }
  ]
}
```
