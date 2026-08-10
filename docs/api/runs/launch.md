# POST /api/v1/runs

Launch a Nextflow / AWS Batch pipeline run. **Lead-only.**

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `bioinformatics_lead` |
| Success | `201 Created` |

## Request model (`RunCreateRequest`)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `pipelineId` | `string` | yes | Catalog id |
| `pipelineVersion` | `string` | no | default `latest` |
| `sampleIds` | `uuid[]` | no | default `[]` |
| `sequencingRunId` | `uuid?` | no | |
| `parameters` | `object` | no | Merged over catalog defaults |
| `runName` | `string?` | no | ≤ 255 chars |

## Response model (`PipelineJobRead`)

| Field | Type | Description |
| --- | --- | --- |
| `id` | `uuid` | Run id |
| `workspace` | `string` | Workspace |
| `pipelineId` | `string` | Catalog id |
| `pipelineName` | `string` | Display name |
| `pipelineVersion` | `string` | Resolved version |
| `status` | `JobStatus` | Job status |
| `sequencingRunId` | `uuid?` | Linked sequencing run |
| `sampleIds` | `any[]` | Sample ids (stored as strings) |
| `parameters` | `object` | Merged params |
| `awsBatchJobId` | `string?` | Batch job id |
| `nextflowRunName` | `string?` | Nextflow run name |
| `workDir` | `string?` | Work directory |
| `launchedBy` | `uuid?` | User id |
| `createdAt` | `datetime` | Created |
| `updatedAt` | `datetime` | Updated |
| `startedAt` | `datetime?` | Started |
| `finishedAt` | `datetime?` | Finished |
| `outputFiles` | `RunOutputFileRead[]` | Placeholder outputs |

## Example

```bash
curl -s -X POST 'http://localhost:8000/api/v1/runs' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-LabChain-Workspace: demo' \
  -H 'Content-Type: application/json' \
  -d '{
    "pipelineId": "rnaseq",
    "pipelineVersion": "latest",
    "sampleIds": ["11111111-1111-1111-1111-111111111111"],
    "parameters": { "aligner": "star_salmon" },
    "runName": "RNA-001-rnaseq"
  }'
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
  "parameters": {
    "aligner": "star_salmon",
    "fasta": null,
    "gtf": null
  },
  "awsBatchJobId": "sim-job-123",
  "nextflowRunName": "RNA-001-rnaseq",
  "workDir": "s3://labchain-biologics/demo/work/...",
  "launchedBy": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "createdAt": "2026-08-10T12:00:00Z",
  "updatedAt": "2026-08-10T12:00:00Z",
  "startedAt": "2026-08-10T12:00:00Z",
  "finishedAt": null,
  "outputFiles": []
}
```
