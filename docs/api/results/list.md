# GET /api/v1/results

List run output files for the current workspace.

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
| `runId` | `uuid?` | — | Filter by pipeline job |
| `fileType` | `OutputFileType?` | — | `vcf`, `bam`, `multiqc`, `other` |

## Response model (`RunOutputFileRead[]`)

| Field | Type | Description |
| --- | --- | --- |
| `id` | `uuid` | Output file id |
| `fileType` | `OutputFileType` | File kind |
| `filename` | `string` | Filename |
| `s3Key` | `string` | Object key |
| `sizeBytes` | `int` | Size |
| `md5` | `string?` | Checksum |
| `sampleId` | `uuid?` | Linked sample |
| `metadata` | `object` | Extra metadata |
| `downloadUrl` | `string?` | Presigned GET URL |
| `createdAt` | `datetime` | Created |

## Example

```bash
curl -s 'http://localhost:8000/api/v1/results?fileType=vcf' \
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
  }
]
```
