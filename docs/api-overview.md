# API overview

Base URL (local): `http://localhost:8000`
API prefix: `/api/v1`

## Authentication

Most routes under `/api/v1` expect:

```http
Authorization: Bearer <access_token>
X-LabChain-Workspace: <workspace-slug>
```

Workspaces are tenants. The header must name a workspace the user is a **member** of;
otherwise the API answers `404 Workspace '<slug>' not found`, exactly as for a workspace that
does not exist. Roles are held **per workspace**: the same user can be `bioinformatics_lead`
in one workspace and `lab_technician` in another. `/auth/*` routes and `GET/POST /workspaces`
do not use the header.

JSON bodies and responses use **camelCase** aliases (`sampleCode`, `rinDin`, `accessToken`, …).

| Role | Typical permissions |
| --- | --- |
| `lab_technician` | Samples, FASTQ, browse pipelines / runs / results |
| `bioinformatics_lead` | Above + pipeline run launch |

The OpenAPI contract is committed as `openapi.json`. Each `operationId` is the endpoint
function name (`list_samples`, `launch_run`, …), stable across releases for generated clients.

Interactive OpenAPI UI: [`/docs`](http://localhost:8000/docs) · ReDoc: [`/redoc`](http://localhost:8000/redoc)

## Endpoint index

| Area | Endpoints |
| --- | --- |
| [Health](api/health.md) | `GET /health` |
| [Auth](api/auth/login.md) | login, me, logout, register |
| [Workspaces](api/workspaces/create.md) | list mine, create, members (list, add, change role, remove) |
| [Samples](api/samples/list.md) | list, create, import, bulk, get, update, delete |
| [Sequencing runs](api/sequencing-runs/index.md) | list, create, get |
| [FASTQ](api/fastq/list.md) | list, get, register, verify |
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
