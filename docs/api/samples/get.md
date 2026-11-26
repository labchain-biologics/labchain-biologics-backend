# GET /api/v1/samples/{sample_id}

Fetch a single sample by id in the current workspace.

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `200 OK` |

## Request model

### Path

| Param | Type | Required |
| --- | --- | --- |
| `sample_id` | `uuid` | yes |

No body.

## Response model (`SampleRead`)

See [GET /samples](list.md).

## Example

```bash
curl -s 'http://localhost:8000/api/v1/samples/11111111-1111-1111-1111-111111111111' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-Titerlane-Workspace: demo'
```

```json
{
  "id": "11111111-1111-1111-1111-111111111111",
  "sampleCode": "RNA-001",
  "patientId": "P-42",
  "projectCode": "PROJ-OMICS",
  "modality": "transcriptomics",
  "tissueType": "blood",
  "collectionDate": "2026-08-01",
  "rinDin": 8.4,
  "concentrationNgUl": 125.5,
  "volumeUl": 40,
  "qcStatus": "pass",
  "qcNotes": null,
  "metadata": {},
  "workspace": "demo",
  "createdAt": "2026-08-10T12:00:00Z",
  "updatedAt": "2026-08-10T12:00:00Z"
}
```
