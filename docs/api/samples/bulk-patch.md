# PATCH /api/v1/samples/bulk

Apply partial updates to multiple samples in one request.

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `200 OK` |

## Request model (`SampleBulkPatchRequest`)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `items` | `SampleBulkPatchItem[]` | yes | min length 1 |

### `SampleBulkPatchItem`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `uuid` | yes | Sample id |
| `patch` | `SampleUpdate` | yes | Partial fields only |

### `SampleUpdate` (all optional)

| Field | Type |
| --- | --- |
| `sampleCode` | `string?` |
| `patientId` | `string?` |
| `projectCode` | `string?` |
| `modality` | `OmicsModality?` |
| `tissueType` | `string?` |
| `collectionDate` | `string?` |
| `rinDin` | `float?` |
| `concentrationNgUl` | `float?` |
| `volumeUl` | `float?` |
| `qcStatus` | `QcStatus?` |
| `qcNotes` | `string?` |
| `metadata` | `object?` |

## Response model (`SampleRead[]`)

Updated samples in request order.

## Example

```bash
curl -s -X PATCH 'http://localhost:8000/api/v1/samples/bulk' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-LabChain-Workspace: demo' \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {
        "id": "11111111-1111-1111-1111-111111111111",
        "patch": { "qcStatus": "pass", "rinDin": 9.1 }
      }
    ]
  }'
```

```json
[
  {
    "id": "11111111-1111-1111-1111-111111111111",
    "sampleCode": "RNA-001",
    "patientId": "P-42",
    "projectCode": "PROJ-OMICS",
    "modality": "transcriptomics",
    "tissueType": "blood",
    "collectionDate": "2026-08-01",
    "rinDin": 9.1,
    "concentrationNgUl": 125.5,
    "volumeUl": 40,
    "qcStatus": "pass",
    "qcNotes": null,
    "metadata": {},
    "workspace": "demo",
    "createdAt": "2026-08-10T12:00:00Z",
    "updatedAt": "2026-08-10T12:05:00Z"
  }
]
```
