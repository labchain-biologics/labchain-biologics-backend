# API overview

Base URL (local): `http://localhost:8000`
API prefix: `/api/v1`

## Authentication

Most routes under `/api/v1` expect:

```http
Authorization: Bearer <access_token>
X-LabChain-Workspace: <workspace-id>
```

JSON bodies and responses use **camelCase** aliases (`sampleCode`, `rinDin`, `accessToken`, …).

| Role | Typical permissions |
| --- | --- |
| `lab_technician` | Samples, FASTQ, browse pipelines / runs / results |
| `bioinformatics_lead` | Above + pipeline run launch |

Interactive OpenAPI UI: [`/docs`](http://localhost:8000/docs) · ReDoc: [`/redoc`](http://localhost:8000/redoc)

## Endpoint index

| Area | Endpoints |
| --- | --- |
| [Health](api/health.md) | `GET /health` |
| [Auth](api/auth/login.md) | login, me, logout, register |
| [Samples](api/samples/list.md) | list, create, import, bulk, get, update, delete |
| [FASTQ](api/fastq/register.md) | register, verify |
| [Pipelines](api/pipelines/list.md) | catalog list + get |
| [Runs](api/runs/launch.md) | launch, list, get, SSE logs |
| [Results](api/results/list.md) | list, by run, download URL |

## Shared enums

| Enum | Values |
| --- | --- |
| `Role` | `lab_technician`, `bioinformatics_lead` |
| `OmicsModality` | `genomics`, `transcriptomics`, `epigenomics`, `proteomics`, `metabolomics`, `multiomics` |
| `QcStatus` | `pending`, `pass`, `fail`, `warn` |
| `JobStatus` | `pending`, `submitted`, `running`, `succeeded`, `failed`, `cancelled` |
| `OutputFileType` | `vcf`, `bam`, `multiqc`, `other` |
| `FastqVerificationStatus` | `pending`, `verified`, `mismatch` |
