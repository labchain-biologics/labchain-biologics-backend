# Architecture

## Project layout

```text
app/
  api/          # FastAPI routers & dependencies (thin)
  core/         # settings, DB engine, security
  models/       # SQLAlchemy 2.0 mapped models
  schemas/      # Pydantic v2 (camelCase aliases)
  services/     # S3, Batch, audit, pipeline catalog
alembic/        # migrations
docs/           # MkDocs source
scripts/        # LocalStack init
```

## Conventions

- All I/O paths are async (DB, HTTP). Sync boto3 calls stay thin inside services.
- SQLAlchemy 2.0 `Mapped[]` / `mapped_column` only.
- Pydantic schemas expose camelCase aliases via `populate_by_name=True`.
- Audit trail rows are append-only (`audit_service.record`) — never mutate or delete.
- RBAC via `RequireRole`: pipeline launch is `bioinformatics_lead` only.
- Multi-tenant scoping via `X-LabChain-Workspace` (also allowed in CORS).
- Endpoint modules stay thin; AWS/S3/Batch logic lives in `app/services/`.
