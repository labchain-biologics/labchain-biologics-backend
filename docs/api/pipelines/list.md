# GET /api/v1/pipelines

List nf-core pipelines from the in-memory catalog.

| | |
| --- | --- |
| Auth | Bearer |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `200 OK` |

## Request model

No body or query parameters. Workspace header may be sent but is not required for catalog reads.

## Response model (`PipelineCatalogItem[]`)

| Field | Type | Description |
| --- | --- | --- |
| `id` | `string` | Catalog id (e.g. `rnaseq`) |
| `name` | `string` | Display name (`nf-core/rnaseq`) |
| `description` | `string` | Summary |
| `version` | `string` | Default version |
| `nfCore` | `bool` | Always `true` for catalog entries |
| `categories` | `string[]` | Tags |
| `defaultParams` | `object` | Default Nextflow params |

## Example

```bash
curl -s 'http://localhost:8000/api/v1/pipelines' \
  -H 'Authorization: Bearer <access_token>'
```

```json
[
  {
    "id": "rnaseq",
    "name": "nf-core/rnaseq",
    "description": "RNA sequencing analysis pipeline using STAR, RSEM, HISAT2 or Salmon.",
    "version": "3.14.0",
    "nfCore": true,
    "categories": ["transcriptomics", "rna"],
    "defaultParams": {
      "aligner": "star_salmon",
      "fasta": null,
      "gtf": null
    }
  }
]
```
