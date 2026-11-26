# GET /api/v1/results/{output_id}/download

Return a fresh S3 presigned download URL for an output file.

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `200 OK` |

## Request model

### Path

| Param | Type | Required |
| --- | --- | --- |
| `output_id` | `uuid` | yes |

No body.

## Response model (`ResultDownloadResponse`)

| Field | Type | Description |
| --- | --- | --- |
| `id` | `uuid` | Output file id |
| `fileType` | `OutputFileType` | File kind |
| `filename` | `string` | Filename |
| `downloadUrl` | `string` | Presigned GET URL |
| `expiresIn` | `int` | TTL in seconds (`S3_PRESIGN_EXPIRE_SECONDS`) |
| `md5` | `string?` | Checksum if known |

## Example

```bash
curl -s 'http://localhost:8000/api/v1/results/dddddddd-dddd-dddd-dddd-dddddddddddd/download' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-Titerlane-Workspace: demo'
```

```json
{
  "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
  "fileType": "vcf",
  "filename": "RNA-001-rnaseq.vcf.gz",
  "downloadUrl": "http://localhost:4566/titerlane-biologics/demo/results/.../variants.vcf.gz?X-Amz-Algorithm=...",
  "expiresIn": 3600,
  "md5": null
}
```
