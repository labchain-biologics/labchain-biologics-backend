# POST /api/v1/fastq/{fastq_id}/verify

Compute the MD5 of the uploaded object and compare it with `expectedMd5`.

The digest comes from the object itself: the ETag for single-part uploads (which is the
content MD5), otherwise the object is streamed and hashed. `sizeBytes` is updated to the
stored size. Without `expectedMd5` the file is `verified` and the computed digest is
recorded. Returns `409` if the file has not been uploaded yet, `422` if the record points
outside the workspace storage namespace.

The ETag of the verified object version is stored. A pipeline launch re-checks it and refuses
files replaced since verification. ETags of SSE-KMS / SSE-C objects are not content MD5s:
those objects are always streamed and hashed.

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
  -H 'X-Titerlane-Workspace: demo'
```

```json
{
  "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "expectedMd5": "d41d8cd98f00b204e9800998ecf8427e",
  "computedMd5": "d41d8cd98f00b204e9800998ecf8427e",
  "verificationStatus": "verified"
}
```
