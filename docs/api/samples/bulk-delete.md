# DELETE /api/v1/samples/bulk

Delete multiple samples by id (soft delete, one `bulk_delete` audit entry per sample). Ids
that are unknown, already deleted or in another workspace are skipped.

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
| Success | `200 OK` |

## Request model (`SampleBulkDeleteRequest`)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `ids` | `uuid[]` | yes | min length 1 |

## Response model

| Field | Type | Description |
| --- | --- | --- |
| `deleted` | `int` | Number of samples deleted by this request |

## Example

```bash
curl -s -X DELETE 'http://localhost:8000/api/v1/samples/bulk' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-LabChain-Workspace: demo' \
  -H 'Content-Type: application/json' \
  -d '{
    "ids": [
      "11111111-1111-1111-1111-111111111111",
      "22222222-2222-2222-2222-222222222222"
    ]
  }'
```

```json
{
  "deleted": 2
}
```
