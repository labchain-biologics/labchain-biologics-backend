# POST /api/v1/fastq/register

Register a FastQ object and receive an S3 presigned upload URL.

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `201 Created` |

## Request model (`FastqRegisterRequest`)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `filename` | `string` | yes | 1–512 chars |
| `s3Key` | `string?` | no | Auto-generated if omitted |
| `sizeBytes` | `int` | no | default `0`, ≥ 0 |
| `expectedMd5` | `string?` | no | Hex MD5 (≤ 32 chars) |
| `sampleId` | `uuid?` | no | Linked sample |
| `sequencingRunId` | `uuid?` | no | Linked sequencing run |
| `readPair` | `string?` | no | e.g. `R1` / `R2` |

## Response model (`FastqRegisterResponse`)

| Field | Type | Description |
| --- | --- | --- |
| `id` | `uuid` | FastQ record id |
| `filename` | `string` | Original filename |
| `s3Key` | `string` | Object key |
| `sizeBytes` | `int` | Declared size |
| `expectedMd5` | `string?` | Expected MD5 |
| `verificationStatus` | `FastqVerificationStatus` | Initially `pending` |
| `uploadUrl` | `string` | Presigned PUT URL |
| `workspace` | `string` | Workspace |
| `createdAt` | `datetime` | Created |

## Example

```bash
curl -s -X POST 'http://localhost:8000/api/v1/fastq/register' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-LabChain-Workspace: demo' \
  -H 'Content-Type: application/json' \
  -d '{
    "filename": "RNA-001_R1.fastq.gz",
    "sizeBytes": 104857600,
    "expectedMd5": "d41d8cd98f00b204e9800998ecf8427e",
    "sampleId": "11111111-1111-1111-1111-111111111111",
    "readPair": "R1"
  }'
```

```json
{
  "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "filename": "RNA-001_R1.fastq.gz",
  "s3Key": "demo/fastq/RNA-001_R1.fastq.gz",
  "sizeBytes": 104857600,
  "expectedMd5": "d41d8cd98f00b204e9800998ecf8427e",
  "verificationStatus": "pending",
  "uploadUrl": "http://localhost:4566/labchain-biologics/demo/fastq/RNA-001_R1.fastq.gz?X-Amz-Algorithm=...",
  "workspace": "demo",
  "createdAt": "2026-08-10T12:00:00Z"
}
```
