# LabChain Biologics Backend

FastAPI async backend for **LabChain Biologics** — a regulated multi-omics LIMS and Nextflow orchestration platform with 21 CFR Part 11–style append-only audit trails.

## Stack

| Layer | Technology |
| --- | --- |
| API | FastAPI (async) + Uvicorn |
| Validation | Pydantic v2 + pydantic-settings |
| Database | PostgreSQL 16, SQLAlchemy 2.0 Async ORM, asyncpg, Alembic |
| Auth | PyJWT (HS256), bcrypt, optional Google OAuth ID tokens |
| Object storage | S3 via Boto3 (LocalStack in local dev) |
| Pipelines | AWS Batch / Nextflow hooks |
| Streaming | sse-starlette (run log SSE) |

Python **3.11+** required. Package manager: [uv](https://docs.astral.sh/uv/).

## Features

- Sample LIMS (modality, RIN/DIN, concentration, QC status)
- FASTQ upload via S3 presigned URLs
- nf-core pipeline catalog and run orchestration (lead-only launch)
- Run status + SSE log streaming
- Result downloads (VCF, BAM, MultiQC, etc.)
- RBAC: `lab_technician` vs `bioinformatics_lead`
- Multi-tenant workspace via `X-LabChain-Workspace`
- Append-only audit trail on mutations

## Next steps

1. [Getting started](getting-started.md) — run the API locally
2. [API overview](api-overview.md) — route map, enums, and per-endpoint docs
3. [Configuration](configuration.md) — environment variables
4. [Development](development.md) — tests, lint, docs
5. [Architecture](architecture.md) — project layout and conventions
