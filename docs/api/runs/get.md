# GET /api/v1/runs/{run_id}

Fetch a single pipeline run, including its registered output files.

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

| Field | Type | Description |
| --- | --- | --- |
| `id` | `uuid` | Run id |
| `workspace` | `string` | Workspace slug |
| `pipelineId` / `pipelineName` / `pipelineVersion` | `string` | nf-core pipeline and revision |
| `status` | `JobStatus` | `pending` (not submitted), `submitted`, `running`, `succeeded`, `failed`, `cancelled` |
| `sampleIds` | `uuid[]` | Samples in the samplesheet |
| `parameters` | `object` | Pipeline parameters passed to Nextflow |
| `awsBatchJobId` | `string?` | AWS Batch head job; `null` when not submitted |
| `executionSubmitted` | `bool` | `true` when the run was submitted to AWS Batch; `false` when pipeline execution is disabled on the instance (`AWS_BATCH_ENABLED=false`): the run is never executed and stays `pending` |
| `nextflowRunName` | `string?` | `-name` given to Nextflow |
| `workDir` / `outputDir` | `string?` | Nextflow work and output directories (`s3://…`) |
| `samplesheetUri` | `string?` | Generated samplesheet |
| `progress` | `object` | From weblog events: `processesSubmitted`, `processesCompleted`, `processesFailed`, `currentProcess`, `lastEvent`, `lastEventAt`, `errorMessage` |
| `launchedBy` | `uuid?` | User who launched the run |
| `createdAt` / `updatedAt` / `startedAt` / `finishedAt` | `datetime?` | ISO-8601 |
| `outputFiles` | `RunOutputFileRead[]` | Files found in `outputDir` when the run finished |

## Example

```bash
curl -s 'http://localhost:8000/api/v1/runs/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-Titerlane-Workspace: demo'
```

```json
{
  "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  "workspace": "demo",
  "pipelineId": "rnaseq",
  "pipelineName": "nf-core/rnaseq",
  "pipelineVersion": "3.14.0",
  "status": "succeeded",
  "sequencingRunId": null,
  "sampleIds": ["11111111-1111-1111-1111-111111111111"],
  "parameters": { "aligner": "star_salmon", "genome": "GRCh38" },
  "awsBatchJobId": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "executionSubmitted": true,
  "nextflowRunName": "lc-rnaseq-bbbbbbbbbbbb",
  "workDir": "s3://titerlane-biologics/nextflow-work/demo/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  "outputDir": "s3://titerlane-biologics/demo/results/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  "samplesheetUri": "s3://titerlane-biologics/demo/runs/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/samplesheet.csv",
  "progress": { "processesCompleted": 42, "lastEvent": "completed" },
  "launchedBy": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "createdAt": "2026-08-10T12:00:00Z",
  "updatedAt": "2026-08-10T14:10:00Z",
  "startedAt": "2026-08-10T12:02:00Z",
  "finishedAt": "2026-08-10T14:10:00Z",
  "outputFiles": [
    {
      "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
      "fileType": "multiqc",
      "filename": "multiqc_report.html",
      "s3Key": "demo/results/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/multiqc/star_salmon/multiqc_report.html",
      "sizeBytes": 4812000,
      "md5": null,
      "sampleId": null,
      "metadata": { "relativePath": "multiqc/star_salmon/multiqc_report.html" },
      "downloadUrl": "https://…",
      "createdAt": "2026-08-10T14:10:00Z"
    }
  ]
}
```
