# DELETE /api/v1/samples/{sample_id}

Delete a sample. Audited; no response body.

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

## Example

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -X DELETE 'http://localhost:8000/api/v1/samples/11111111-1111-1111-1111-111111111111' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-LabChain-Workspace: demo'
```

```text
204
```
