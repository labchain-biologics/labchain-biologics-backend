# Titerlane Biologics Backend

FastAPI async backend for **Titerlane Biologics** — a regulated multi-omics LIMS and Nextflow orchestration platform with 21 CFR Part 11–style append-only audit trails.

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
- nf-core pipeline catalog and run orchestration (lead-only launch): samplesheet generated
  from verified FASTQ files, Nextflow head job submitted to AWS Batch
- Run status from Nextflow weblog events and AWS Batch polling; output files registered
  from the run's S3 output directory
- Run log as JSON and SSE stream
- FASTQ integrity: MD5 computed from the stored object
- Result downloads (VCF, BAM, MultiQC, etc.)
- RBAC: `lab_technician` vs `bioinformatics_lead`
- Multi-tenant workspaces with per-workspace roles (`X-Titerlane-Workspace` = workspace slug)
- Append-only audit trail on mutations

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Docker & Docker Compose (Postgres + LocalStack)

## Quick start

### 1. Clone and install

```bash
git clone <repo-url>
cd titerlane-biologics-backend
uv sync --extra dev
```

### 2. Environment

```bash
cp .env.example .env
```

Edit `.env` if needed. Defaults target local Postgres and LocalStack.
Set `SECRET_KEY` to a strong random value before starting the API.

### 3. Infrastructure

```bash
docker compose --env-file .env up -d
```

Starts:

- **Postgres** on `localhost:5433` (`titerlane` / `titerlane` / `titerlane`)
- **LocalStack** S3 on `localhost:4566` (bucket `titerlane-biologics` created on init)

To stop the local infrastructure:

```bash
docker compose --env-file .env stop
```

### 4. Migrations

```bash
uv run poe migrate
```

Upgrading an existing database past migration 0003 creates workspaces from existing data
but **no memberships** (historical activity does not prove who should have access). Grant
access explicitly:

```bash
uv run python scripts/grant_membership.py --email lead@lab.org \
  --workspace <slug> --role bioinformatics_lead
```

Migration 0005 resets every FASTQ verification to `pending` (the previous check did not read
the stored bytes): verify the files again before launching runs.

### 5. Run the API

```bash
uv run poe start-dev
```

| Resource | URL |
| --- | --- |
| Health | http://localhost:8000/health |
| OpenAPI docs | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| API prefix | `/api/v1` |

Default CORS origin for the Vite frontend: `http://localhost:5173`.

## Self-hosting

A container image is published to GitHub Container Registry
(`ghcr.io/titerlane-biologics/titerlane-biologics-backend`), with a production Docker Compose
setup in [`deploy/`](deploy/) (Postgres, one-shot migrations, Docker secrets). See the
[self-hosting guide](docs/self-hosting.md).

## API overview

All authenticated routes expect:

```http
Authorization: Bearer <access_token>
X-Titerlane-Workspace: <workspace-slug>
```

| Area | Prefix | Notes |
| --- | --- | --- |
| Auth | `/api/v1/auth` | login, register, me (with memberships), logout |
| Workspaces | `/api/v1/workspaces`, `/api/v1/members` | create/list workspaces, manage members |
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

## Documentation

MkDocs (Material) sources live in `docs/`. Local preview:

```bash
uv sync --extra dev --extra docs
uv run poe docs-serve
```

On push to `main`, GitHub Actions publishes to GitHub Pages
(`https://titerlane-biologics.github.io/titerlane-biologics-backend/`).

## Configuration

See [`.env.example`](.env.example). Important variables:

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | JWT HS256 secret (≥ 32 chars, required, must not be placeholder) |
| `BOOTSTRAP_REGISTRATION_ENABLED` | Enables `/auth/register` bootstrap flow outside production (default `false`) |
| `WORKSPACE_CREATION_ENABLED` | Lets any authenticated user create a workspace (default `true`) |
| `DATABASE_URL` | Async Postgres URL (`postgresql+asyncpg://…`) |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `S3_ENDPOINT_URL` | LocalStack (`http://localhost:4566`) or empty for real AWS |
| `AWS_BATCH_ENABLED` | Submit runs to AWS Batch; `false` records runs without executing them |
| `PUBLIC_API_URL` | URL Nextflow can reach for weblog callbacks (optional) |
| `GOOGLE_CLIENT_ID` | Audience for Google ID token login (optional) |

## Roles

Roles are granted per workspace (`workspace_memberships`).

| Role | Typical permissions |
| --- | --- |
| `lab_technician` | Samples, FASTQ, browse pipelines/results |
| `bioinformatics_lead` | Above + pipeline run launch + workspace member management |

## Contributing and security

- Report vulnerabilities privately: see [SECURITY.md](SECURITY.md).
- Contributions: see [CONTRIBUTING.md](CONTRIBUTING.md) (external code contributions open once a CLA is in place).
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

Copyright (C) 2026 Titerlane Biologics.

This program is free software: you can redistribute it and/or modify it under the terms of
the [GNU Affero General Public License v3.0](LICENSE) (`AGPL-3.0-only`).

In short: you may use, modify and self-host it. If you run a modified version as a network
service, you must offer its users the corresponding source code under the same license.

### Python SDK: Apache-2.0

The Python SDK in [`sdk/`](sdk/) (`titerlane-biologics-sdk`) is **not** under the AGPL: it is
licensed under the [Apache License 2.0](sdk/LICENSE) (`Apache-2.0`). It contains no server
code and only talks to the server over its public HTTP API, so scripts, notebooks and
applications that import it can use any licence, including proprietary ones.

| Path | Licence |
| --- | --- |
| `sdk/` | Apache-2.0 ([`sdk/LICENSE`](sdk/LICENSE)) |
| Everything else (server, migrations, docs, scripts, tests) | AGPL-3.0-only ([`LICENSE`](LICENSE)) |
