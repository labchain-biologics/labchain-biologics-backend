# Getting started

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Docker & Docker Compose (Postgres + LocalStack)

## 1. Clone and install

```bash
git clone https://github.com/titerlane-biologics/titerlane-biologics-backend.git
cd titerlane-biologics-backend
uv sync --extra dev
```

## 2. Environment

```bash
cp .env.example .env
```

Edit `.env` if needed. Defaults target local Postgres and LocalStack.

## 3. Infrastructure

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

## 4. Migrations

```bash
uv run poe migrate
```

## 5. Run the API

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
