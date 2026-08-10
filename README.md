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

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Docker & Docker Compose (Postgres + LocalStack)

## Quick start

### 1. Clone and install

```bash
git clone <repo-url>
cd labchain-biologics-backend
uv sync --extra dev
```

### 2. Environment

```bash
cp .env.example .env
```

Edit `.env` if needed. Defaults target local Postgres and LocalStack.

### 3. Infrastructure

```bash
docker compose up -d
```

Starts:

- **Postgres** on `localhost:5432` (`labchain` / `labchain` / `labchain`)
- **LocalStack** S3 on `localhost:4566` (bucket `labchain-biologics` created on init)

### 4. Migrations

```bash
uv run poe migrate
```

### 5. Run the API

```bash
uv run start-dev
```

| Resource | URL |
| --- | --- |
| Health | http://localhost:8000/health |
| OpenAPI docs | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| API prefix | `/api/v1` |

Default CORS origin for the Vite frontend: `http://localhost:5173`.

## API overview

All authenticated routes expect:

```http
Authorization: Bearer <access_token>
X-LabChain-Workspace: <workspace-id>
```

| Area | Prefix | Notes |
| --- | --- | --- |
| Auth | `/api/v1/auth` | login, register, me, logout |
| Samples | `/api/v1/samples` | CRUD, CSV import, bulk update/delete |
| FASTQ | `/api/v1/fastq` | presign + verify |
| Pipelines | `/api/v1/pipelines` | nf-core catalog |
| Runs | `/api/v1/runs` | launch (lead-only), list, SSE logs |
| Results | `/api/v1/results` | list outputs, download URLs |

## Project layout

```
app/
  api/          # FastAPI routers & dependencies (thin)
  core/         # settings, DB engine, security
  models/       # SQLAlchemy 2.0 mapped models
  schemas/      # Pydantic v2 (camelCase aliases)
  services/     # S3, Batch, audit, pipeline catalog
alembic/        # migrations
scripts/        # LocalStack init
```

## Development

```bash
# Pre-commit
uv run poe check

# Tests
uv run poe test
```

## Configuration

See [`.env.example`](.env.example). Important variables:

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | JWT HS256 secret (≥ 32 chars) |
| `DATABASE_URL` | Async Postgres URL (`postgresql+asyncpg://…`) |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `S3_ENDPOINT_URL` | LocalStack (`http://localhost:4566`) or empty for real AWS |
| `AWS_BATCH_ENABLED` | `false` locally; enable in deployed environments |
| `GOOGLE_CLIENT_ID` | Audience for Google ID token login (optional) |

## Roles

| Role | Typical permissions |
| --- | --- |
| `lab_technician` | Samples, FASTQ, browse pipelines/results |
| `bioinformatics_lead` | Above + pipeline run launch |

## License

Proprietary — LabChain Biologics. All rights reserved.
