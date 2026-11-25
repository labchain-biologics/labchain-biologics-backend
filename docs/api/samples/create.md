# POST /api/v1/samples

Create a sample in the current workspace. `sampleCode` is unique per workspace (`409` on
conflict). `status` and `createdBy` are set by the server: a new sample is `registered`.

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
| `modality` | `OmicsModality` | yes | genomics, transcriptomics, epigenomics, proteomics, metabolomics, multiomics |
| `assay` | `SampleAssay?` | no | wgs, exome, targeted_panel, bulk_rna, single_cell_rna, atac_seq, methylation, amplicon_16s, metagenomics |
| `sampleType` | `SampleType?` | no | tumor, normal, control, environmental, cell_line |
| `tissueType` | `string?` | no | |
| `organism` | `string?` | no | |
| `collectionDate` | `string?` | no | |
| `biobankId` | `string?` | no | |
| `pairedGroup` | `string?` | no | Tumor/normal pair, time point or replicate group |
| `platform` | `string?` | no | e.g. Illumina NovaSeq 6000 |
| `libraryPrepKit` | `string?` | no | |
| `targetPanel` | `string?` | no | Panel / BED file name |
| `indexId` | `string?` | no | Index / barcode id |
| `rinDin` | `float?` | no | 0–10 |
| `concentrationNgUl` | `float?` | no | ≥ 0 |
| `volumeUl` | `float?` | no | ≥ 0 |
| `a260280` | `float?` | no | 0–5 |
| `qcStatus` | `QcStatus` | no | default `pending` |
| `qcNotes` | `string?` | no | |
| `notes` | `string?` | no | Free text |
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
  "status": "registered",
  "createdBy": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "createdAt": "2026-08-10T12:00:00Z",
  "updatedAt": "2026-08-10T12:00:00Z"
}
```
