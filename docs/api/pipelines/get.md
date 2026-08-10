# GET /api/v1/pipelines/{pipeline_id}

Fetch a single pipeline from the nf-core catalog.

| | |
| --- | --- |
| Auth | Bearer |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `200 OK` |

## Request model

### Path

| Param | Type | Required | Notes |
| --- | --- | --- | --- |
| `pipeline_id` | `string` | yes | e.g. `rnaseq`, `sarek`, `atacseq` |

No body.

## Response model (`PipelineCatalogItem`)

See [GET /pipelines](list.md).

## Example

```bash
curl -s 'http://localhost:8000/api/v1/pipelines/sarek' \
  -H 'Authorization: Bearer <access_token>'
```

```json
{
  "id": "sarek",
  "name": "nf-core/sarek",
  "description": "Analysis pipeline to detect germline or somatic variants from WGS/WES.",
  "version": "3.4.0",
  "nfCore": true,
  "categories": ["genomics", "variant-calling"],
  "defaultParams": {
    "tools": "haplotypecaller",
    "genome": "GATK.GRCh38"
  }
}
```
