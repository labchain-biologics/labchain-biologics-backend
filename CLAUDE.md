# CLAUDE.md — labchain-biologics-backend

Open-source (AGPL-3.0-only, see `LICENSE`) FastAPI backend for LabChain Biologics: multi-omics LIMS, nf-core/Nextflow
orchestration, append-only audit trail. Consumed by the proprietary `omicsflow-forge` frontend
but must stay fully usable on its own through its public API.

## Commands

```bash
uv sync --extra dev            # install
uv run poe start-local-run     # Postgres (5433) + LocalStack S3 (4566) via docker compose
uv run poe migrate             # alembic upgrade head
uv run poe start-dev           # API on :8000 (reload)
uv run poe test                # pytest
uv run poe check               # pre-commit: ruff, ruff-format, mypy --strict, markdownlint
uv run poe e2e                 # end-to-end walkthrough against a running API
uv run poe docs-serve          # MkDocs (needs --extra docs)
uv sync --all-packages --extra dev   # also installs the Python SDK (sdk/)
uv run poe sdk-test            # SDK tests (no network)
uv run poe sdk-typecheck       # mypy --strict on the SDK
```

`SECRET_KEY` (≥ 32 chars, not a placeholder) must be set, including for tests (see `tests/conftest.py`).

## Layout

`app/api` (thin routers + `deps.py`) · `app/core` (settings, DB, security) · `app/models`
(SQLAlchemy 2.0) · `app/schemas` (Pydantic v2) · `app/services` (S3, Batch, audit, catalog) ·
`alembic/versions` · `docs/` (MkDocs, one page per endpoint under `docs/api/`) ·
`sdk/` (Python SDK `labchain-biologics-sdk`, uv workspace member).

### Python SDK (`sdk/`)

- Licensed **Apache-2.0** (`sdk/LICENSE`), unlike the AGPL server. Never import `app.*` from
  the SDK: it mirrors the public contract (`openapi.json`) with its own models.
- Dependencies: `httpx` and `pydantic` only. Synchronous client; mypy --strict.
- An API change that affects a route, field or enum used by the SDK updates `sdk/` in the
  same PR.
- Never log or `repr()` tokens or signed storage URLs; signed URLs never receive the API
  `Authorization` header.
- Unit tests use `httpx.MockTransport` (`sdk/tests/fakes.py`), no network.

## Rules

### Stack and style

- Python 3.11+, FastAPI async, SQLAlchemy 2.0 `Mapped[]`/`mapped_column` only, Pydantic v2.
  Do not add a framework or ORM without being asked.
- `mypy --strict` and ruff (line length 100) must pass. No `# type: ignore` without a reason comment.
- Endpoints stay thin: business logic and any AWS/S3/Batch/Nextflow call live in `app/services/`.
- Blocking boto3 calls are run via `asyncio.to_thread` in new code; never block the event loop
  with long I/O.
- Schemas expose camelCase aliases with
  `ConfigDict(populate_by_name=True, from_attributes=True)`.

### Tenancy and security

- Tenant routes take the workspace through `deps.Workspace` / `deps.Membership`, which verify
  that the user is a member (`workspace_memberships`). Never read `X-LabChain-Workspace` directly.
- Roles are per workspace (`WorkspaceMembership.role`); `User` has no global role.
- Every query on a tenant-owned table filters on `workspace`. A resource from another workspace,
  like a workspace the user is not a member of, returns 404, never its content.
- Authorization goes through `deps.py` (`RequireRole`, `LabOrLead`, `BioinformaticsLead`).
  Never check roles inline in a handler.
- Never log or return secrets, tokens, password hashes or presigned URLs in audit payloads.
- Settings come from `app/core/config.py` (env vars). No hard-coded credentials, bucket names
  or URLs outside defaults meant for local dev.

### Audit trail (21 CFR Part 11)

- Every mutation of a domain entity calls `audit_service.record(...)` in the **same transaction**,
  with `before_state` / `after_state`.
- Never UPDATE or DELETE `audit_logs` (enforced by DB triggers, migration 0002).
- New regulated entities use soft delete (status/flag + audit), not `db.delete`.

### Pipeline execution

- Run status changes only from real signals: Nextflow weblog events (`POST /runs/{id}/events`)
  or AWS Batch status (`run_lifecycle.reconcile_all`). Never fabricate statuses, logs, outputs
  or checksums. With `AWS_BATCH_ENABLED=false` a run stays `pending` and says so in its log.
- Lifecycle transitions go through `app/services/run_lifecycle.py` (idempotent, audited).
- Nextflow arguments are built only by `batch.build_nextflow_command` (argv list, validated
  parameter names, no shell). Samplesheets only by `services/samplesheet.py`.
- Secrets (weblog token) never appear in run logs or API responses.

### Database

- Any model change ships with an Alembic migration in `alembic/versions/` (`NNNN_description.py`).
  Never edit a migration that is already on `main`.
- Postgres-specific types (JSONB, native enums) are fine; enum changes need explicit migration SQL.

### Tests and docs

- New or changed endpoints need tests covering: success, validation error, wrong role (403),
  other workspace (404), and the audit record.
- Unit tests (`tests/`) must not need network or AWS; mock services at the `app/services` boundary.
- Integration tests use the `fake_s3` fixture (in-memory S3) and patch `batch_service`; they
  never call AWS.
- Integration tests (`tests/integration/`) run the real app against Postgres
  (`TEST_DATABASE_URL`, default: docker compose DB `labchain_test`) and are skipped when it is
  unreachable. Tenant isolation and RBAC changes must be covered there.
- Update `docs/api/<area>/<endpoint>.md` and `mkdocs.yml` nav when the API changes.

### Open source hygiene

- This repo is public-facing: no customer data, internal hostnames, account IDs or proprietary
  frontend code. Paid-only features must sit behind an explicit edition/entitlement boundary.
- No placeholder or stub behaviour presented as real. Simulated paths (e.g. Batch disabled)
  must be flagged (`simulated=True`, config flag) and documented.
