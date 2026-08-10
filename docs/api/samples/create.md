# POST /api/v1/samples

Create a sample in the current workspace.

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `201 Created` |

## Request model (`SampleCreate`)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `sampleCode` | `string` | yes | 1–128 chars |
| `patientId` | `string?` | no | |
| `projectCode` | `string?` | no | |
| `modality` | `OmicsModality` | yes | |
| `tissueType` | `string?` | no | |
| `collectionDate` | `string?` | no | |
| `rinDin` | `float?` | no | 0–10 |
| `concentrationNgUl` | `float?` | no | ≥ 0 |
| `volumeUl` | `float?` | no | ≥ 0 |
| `qcStatus` | `QcStatus` | no | default `pending` |
| `qcNotes` | `string?` | no | |
| `metadata` | `object` | no | default `{}` |

## Response model (`SampleRead`)

See [GET /samples](list.md).

## Example

```bash
curl -s -X POST 'http://localhost:8000/api/v1/samples' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-LabChain-Workspace: demo' \
  -H 'Content-Type: application/json' \
  -d '{
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
    "metadata": { "batch": "B12" }
  }'
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
  "metadata": { "batch": "B12" },
  "workspace": "demo",
  "createdAt": "2026-08-10T12:00:00Z",
  "updatedAt": "2026-08-10T12:00:00Z"
}
```
