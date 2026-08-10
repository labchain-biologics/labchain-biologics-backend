# GET /api/v1/samples

List samples in the current workspace, with optional filters.

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `200 OK` |

## Request model

No body.

### Query

| Param | Type | Default | Description |
| --- | --- | --- | --- |
| `modality` | `OmicsModality?` | — | Filter by modality |
| `qcStatus` | `QcStatus?` | — | Filter by QC status |
| `limit` | `int` | `100` | 1–1000 |
| `offset` | `int` | `0` | Pagination offset |

## Response model (`SampleRead[]`)

| Field | Type | Description |
| --- | --- | --- |
| `id` | `uuid` | Sample id |
| `sampleCode` | `string` | Lab sample code |
| `patientId` | `string?` | Patient identifier |
| `projectCode` | `string?` | Project code |
| `modality` | `OmicsModality` | Omics modality |
| `tissueType` | `string?` | Tissue type |
| `collectionDate` | `string?` | Collection date (free-form) |
| `rinDin` | `float?` | RIN/DIN (0–10) |
| `concentrationNgUl` | `float?` | Concentration ng/µL |
| `volumeUl` | `float?` | Volume µL |
| `qcStatus` | `QcStatus` | QC status |
| `qcNotes` | `string?` | QC notes |
| `metadata` | `object` | Arbitrary JSON metadata |
| `workspace` | `string` | Workspace id |
| `createdAt` | `datetime` | Created |
| `updatedAt` | `datetime` | Updated |

## Example

```bash
curl -s 'http://localhost:8000/api/v1/samples?modality=transcriptomics&qcStatus=pass&limit=20' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-LabChain-Workspace: demo'
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
]
```
