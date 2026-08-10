# POST /api/v1/fastq/{fastq_id}/verify

Compute / compare MD5 for a registered FastQ and update `verificationStatus`.

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `200 OK` |

## Request model

### Path

| Param | Type | Required |
| --- | --- | --- |
| `fastq_id` | `uuid` | yes |

No body.

## Response model (`FastqVerifyResponse`)

| Field | Type | Description |
| --- | --- | --- |
| `id` | `uuid` | FastQ id |
| `expectedMd5` | `string?` | Expected digest |
| `computedMd5` | `string` | Computed digest |
| `verificationStatus` | `FastqVerificationStatus` | `verified` or `mismatch` |

## Example

```bash
curl -s -X POST 'http://localhost:8000/api/v1/fastq/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/verify' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-LabChain-Workspace: demo'
```

```json
{
  "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "expectedMd5": "d41d8cd98f00b204e9800998ecf8427e",
  "computedMd5": "d41d8cd98f00b204e9800998ecf8427e",
  "verificationStatus": "verified"
}
```
