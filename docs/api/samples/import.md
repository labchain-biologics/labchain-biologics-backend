# POST /api/v1/samples/import

Bulk-create samples from a UTF-8 CSV upload.

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `200 OK` |

## Request model

### Body

`multipart/form-data` with a single file field:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `file` | `file` | yes | `.csv`, UTF-8 (BOM allowed) |

### CSV columns

Accepts camelCase or snake_case headers. Required: `sampleCode` / `sample_code`, `modality`.

| Column | Maps to |
| --- | --- |
| `sampleCode` / `sample_code` | sample code |
| `patientId` / `patient_id` | patient id |
| `projectCode` / `project_code` | project |
| `modality` | modality |
| `tissueType` / `tissue_type` | tissue |
| `collectionDate` / `collection_date` | collection date |
| `rinDin` / `rin_din` | RIN/DIN |
| `concentrationNgUl` / `concentration_ng_ul` | concentration |
| `volumeUl` / `volume_ul` | volume |
| `qcStatus` / `qc_status` | QC (default `pending`) |
| `qcNotes` / `qc_notes` | notes |

## Response model (`SampleImportResult`)

| Field | Type | Description |
| --- | --- | --- |
| `created` | `int` | Rows created |
| `skipped` | `int` | Rows skipped (validation errors) |
| `errors` | `string[]` | Per-row error messages |
| `samples` | `SampleRead[]` | Created samples |

## Example

```bash
curl -s -X POST 'http://localhost:8000/api/v1/samples/import' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-Titerlane-Workspace: demo' \
  -F 'file=@samples.csv'
```

```json
{
  "created": 2,
  "skipped": 1,
  "errors": ["row 4: modality field required"],
  "samples": [
    {
      "id": "11111111-1111-1111-1111-111111111111",
      "sampleCode": "RNA-001",
      "patientId": null,
      "projectCode": null,
      "modality": "transcriptomics",
      "tissueType": null,
      "collectionDate": null,
      "rinDin": null,
      "concentrationNgUl": null,
      "volumeUl": null,
      "qcStatus": "pending",
      "qcNotes": null,
      "metadata": {},
      "workspace": "demo",
      "createdAt": "2026-08-10T12:00:00Z",
      "updatedAt": "2026-08-10T12:00:00Z"
    }
  ]
}
```
