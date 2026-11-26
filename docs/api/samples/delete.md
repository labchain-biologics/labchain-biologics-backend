# DELETE /api/v1/samples/{sample_id}

Delete a sample (soft delete). Audited (`delete`, with the full sample before deletion and
`deletedAt` after); no response body.

!!! note "Soft delete"
    Samples are regulated records (21 CFR Part 11): deleting one does not remove it. The sample
    disappears from every endpoint (`404`, absent from listings, unusable for FASTQ or runs),
    but its row, its links to FASTQ files and run outputs, and its audit trail are kept.
    Its sample code stays reserved: creating or importing a sample with the same code answers
    `409` (create) or is skipped (import).

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `204 No Content` |

## Request model

### Path

| Param | Type | Required |
| --- | --- | --- |
| `sample_id` | `uuid` | yes |

No body.

## Response model

Empty body (`204`).

## Errors

| Status | When |
| --- | --- |
| `404` | Unknown sample, already deleted, or in another workspace |

## Example

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -X DELETE 'http://localhost:8000/api/v1/samples/11111111-1111-1111-1111-111111111111' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-Titerlane-Workspace: demo'
```

```text
204
```
