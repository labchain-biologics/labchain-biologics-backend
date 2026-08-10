# DELETE /api/v1/samples/bulk

Delete multiple samples by id. Missing ids are skipped.

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
| `deleted` | `int` | Number of rows deleted |

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
