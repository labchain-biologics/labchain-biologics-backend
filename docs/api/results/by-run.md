# GET /api/v1/results/runs/{run_id}

List output files for a specific pipeline run.

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

## Response model (`RunOutputFileRead[]`)

See [GET /results](list.md).

## Example

```bash
curl -s 'http://localhost:8000/api/v1/results/runs/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-Titerlane-Workspace: demo'
```

```json
[
  {
    "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
    "fileType": "vcf",
    "filename": "RNA-001-rnaseq.vcf.gz",
    "s3Key": "demo/results/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/variants.vcf.gz",
    "sizeBytes": 0,
    "md5": null,
    "sampleId": null,
    "metadata": { "format": "vcf" },
    "downloadUrl": "http://localhost:4566/titerlane-biologics/demo/results/.../variants.vcf.gz?X-Amz-Algorithm=...",
    "createdAt": "2026-08-10T12:00:00Z"
  },
  {
    "id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
    "fileType": "bam",
    "filename": "RNA-001-rnaseq.bam",
    "s3Key": "demo/results/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/aligned.bam",
    "sizeBytes": 0,
    "md5": null,
    "sampleId": null,
    "metadata": { "format": "bam" },
    "downloadUrl": "http://localhost:4566/titerlane-biologics/demo/results/.../aligned.bam?X-Amz-Algorithm=...",
    "createdAt": "2026-08-10T12:00:00Z"
  }
]
```
