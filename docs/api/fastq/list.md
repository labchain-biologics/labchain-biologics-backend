# GET /api/v1/fastq

List FastQ files of the current workspace, newest first. `GET /api/v1/fastq/{id}` returns one.

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `200 OK` |

## Query

| Param | Type | Description |
| --- | --- | --- |
| `sampleId` | `uuid?` | Only files linked to this sample |
| `sequencingRunId` | `uuid?` | Only files of this sequencing run |
| `limit` | `int` | 1–1000, default 200 |
| `offset` | `int` | default 0 |

## Response model (`FastqRead[]`)

| Field | Type | Description |
| --- | --- | --- |
| `id` | `uuid` | FastQ record id |
| `filename` | `string` | File name |
| `s3Key` | `string` | Object key |
| `sizeBytes` | `int` | Size |
| `expectedMd5` | `string?` | MD5 declared at registration |
| `computedMd5` | `string?` | MD5 computed at verification |
| `verificationStatus` | `string` | `pending`, `verified` or `mismatch` |
| `sampleId` | `uuid?` | Linked sample |
| `sequencingRunId` | `uuid?` | Linked sequencing run |
| `readPair` | `string?` | `R1` / `R2` |
| `workspace` | `string` | Workspace slug |
| `createdAt` | `datetime` | ISO-8601 |
