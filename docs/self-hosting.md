# Self-hosting

Run the Titerlane Biologics API in production from the published container image, with
Docker Compose. The API is usable on its own: every feature is reachable through the
[public API](api-overview.md), the [Python SDK](sdk/index.md) and its command line.

For a development setup (LocalStack, reload), see [Getting started](getting-started.md).

## What you deploy

| Component | Provided by | Notes |
| --- | --- | --- |
| API server | `ghcr.io/titerlane-biologics/titerlane-biologics-backend` | One container, non-root, read-only file system |
| Migrations | Same image, `alembic upgrade head` | One-shot container run before each API start |
| PostgreSQL 16 | `deploy/compose.yaml` (or your managed Postgres) | Data in the `pg_data` volume |
| Object storage | **You** (AWS S3 or an S3-compatible service) | FASTQ uploads and run outputs |
| TLS reverse proxy | **You** (Caddy, nginx, Traefik, a load balancer) | The API listens on loopback only |
| Pipeline execution | Optional: AWS Batch | Without it, runs stay `pending` and are never executed |

### Image tags

| Tag | Content |
| --- | --- |
| `X.Y.Z`, `X.Y`, `latest` | Released versions (git tag `vX.Y.Z`) |
| `edge`, `sha-<commit>` | Latest commit on `main`, not a release |

Images are built for `linux/amd64` and `linux/arm64` and carry a signed build provenance
attestation:

```bash
gh attestation verify \
  oci://ghcr.io/titerlane-biologics/titerlane-biologics-backend:<tag> \
  --owner titerlane-biologics
```

Pin a version in production: upgrades should be deliberate (see [Upgrades](#upgrades)).

## 1. Get the deployment files

The files live in [`deploy/`](https://github.com/titerlane-biologics/titerlane-biologics-backend/tree/main/deploy):

```bash
git clone https://github.com/titerlane-biologics/titerlane-biologics-backend.git
cd titerlane-biologics-backend/deploy
cp .env.example .env
```

`.env` holds non-secret configuration only. Set at least `TITERLANE_VERSION`, `CORS_ORIGINS`
and `S3_BUCKET`. All variables are listed in [Configuration](configuration.md).

## 2. Create the secrets

Secrets are files in `deploy/secrets/`, mounted into the containers as Docker secrets under
`/run/secrets/`. The API reads one file per setting, named after it (`SECRETS_DIR`). They
never appear in `.env`, in `docker inspect` output or in the process environment.

```bash
mkdir -p secrets && chmod 700 secrets
pw="$(openssl rand -hex 24)"
printf '%s' "$pw" > secrets/postgres_password
printf 'postgresql+asyncpg://titerlane:%s@postgres:5432/titerlane' "$pw" > secrets/database_url
openssl rand -hex 48 | tr -d '\n' > secrets/secret_key
chmod 444 secrets/*
unset pw
```

| File | Used by | Content |
| --- | --- | --- |
| `secret_key` | API, migrations | JWT signing key, at least 32 characters |
| `database_url` | API, migrations | `postgresql+asyncpg://…`, same password as `postgres_password` |
| `postgres_password` | Postgres | Database password, set on first start only |

!!! note "File permissions"
    Compose mounts secret files with their host permissions, and the containers run as
    unprivileged users (API: uid 10001; Postgres: uid 70). The files must therefore be
    readable inside the container (`444`), and the `secrets/` directory (`700`) is what
    keeps other host users out. `deploy/.gitignore` excludes `secrets/` and `.env`.

`postgres_password` only takes effect when the database volume is first created. To change
it later, run `ALTER USER` in Postgres and update both files.

To use a managed Postgres, remove the `postgres` service and its `depends_on`, and point
`database_url` at your instance.

## 3. Object storage

Create the bucket before starting the API. Browsers upload FASTQ files and download results
straight from storage through presigned URLs, so:

- the storage endpoint must be reachable by your users' browsers, not only by the API;
- the bucket CORS policy must allow your web origins (`PUT`, `GET`, `HEAD`, exposing `ETag`).

**AWS S3.** Leave `S3_ENDPOINT_URL` empty. Prefer an IAM role (EC2 instance profile, ECS
task role) over keys: with `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` unset, the API
uses the standard AWS credential chain. The role needs `s3:GetObject`, `s3:PutObject`,
`s3:ListBucket` on the bucket, plus the AWS Batch permissions if you run pipelines.

**S3-compatible service.** Set `S3_ENDPOINT_URL` to the public endpoint of the service
(path-style addressing is used) and set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`. With
a custom endpoint the API also creates the bucket if it is missing and applies
`CORS_ORIGINS` to it at startup; a service that does not support the bucket CORS API logs a
warning, and you configure CORS on the service itself.

## 4. Start

```bash
docker compose --env-file .env up -d
docker compose ps
curl -s http://127.0.0.1:8000/health
```

Compose starts Postgres, waits until it is healthy, runs the migrations once, then starts
the API. If a migration fails, the API does not start: read `docker compose logs migrate`.

## 5. Reverse proxy and TLS

The API is published on `127.0.0.1:${TITERLANE_PORT}` only. Terminate TLS in front of it,
for example with Caddy:

```text
titerlane.example.org {
    reverse_proxy 127.0.0.1:8000
}
```

Uvicorn trusts `X-Forwarded-*` headers only from the IPs in `FORWARDED_ALLOW_IPS`. When
the proxy is not on the same network namespace as the API (another container, another host),
set it to the proxy address as the API container sees it.

The log stream endpoint (`GET /runs/{id}/logs/stream`) uses server-sent events: disable
response buffering for it if your proxy buffers by default (nginx: `proxy_buffering off`).

## 6. Create the first user

Self-registration (`POST /auth/register`) is always disabled when `APP_ENV=production`.
Create the first account with the `titerlane-admin` operator command, in a one-off container
(it prompts for the password twice):

```bash
docker compose run --rm --no-deps api \
  titerlane-admin create-user --email lead@lab.example --full-name "Lab Lead"
```

The user then logs in through the API and creates a workspace
([`POST /workspaces`](api/workspaces/create.md)), becoming its `bioinformatics_lead`, and
adds members ([`POST /members`](api/workspaces/members.md)). With `GOOGLE_CLIENT_ID` set,
users can also sign in with Google.

See [Operator commands](#operator-commands) to create the workspace from the command line
instead.

Set `WORKSPACE_CREATION_ENABLED=false` once your workspaces exist if users should not create
their own.

## Operations

### Operator commands

`titerlane-admin` runs on the server with its settings and writes every action to the audit
trail, with no user actor and the reason shown below. In Compose, prefix each command with
`docker compose run --rm --no-deps api`.

| Command | Purpose | Audit reason |
| --- | --- | --- |
| `titerlane-admin create-user --email <email> [--full-name <name>]` | Create a password user. Same rules as the API: valid email, 8–128 character password | `operator create-user` |
| `titerlane-admin grant-membership --email <email> --workspace <slug> --role <role> [--create --name <name>]` | Give an active user a role (`lab_technician` or `bioinformatics_lead`) in an active workspace, optionally creating it with the same slug rules as the API. Refuses to demote a workspace's only lead | `operator grant` |

Passwords are never command-line arguments (shell history, process list). Without a
terminal, use `docker compose run -T` with `--password-stdin` and send the password on the
first line of standard input.

### Workers and scaling

The image runs a single Uvicorn worker. With `AWS_BATCH_ENABLED=true` the API process also
polls AWS Batch for run status (`RUN_MONITOR_INTERVAL_SECONDS`); transitions are idempotent,
but running several API replicas multiplies that polling. Scale vertically first.

### Backups

Back up the database (it holds the audit trail) and the bucket. For example:

```bash
docker compose exec -T postgres pg_dump -U titerlane -Fc titerlane > titerlane-$(date +%F).dump
```

Test restores. The `audit_logs` table is append-only (database triggers): restore it with
the rest of the database, never edit it.

### Upgrades

1. Read the release notes, back up the database.
2. Change `TITERLANE_VERSION` in `.env`.
3. `docker compose --env-file .env up -d`: the `migrate` container applies new migrations
   before the new API starts.

Migrations are forward-only; to roll back, restore the backup taken in step 1.

### Logs

```bash
docker compose logs -f api
```

Logs go to stdout; configure your Docker logging driver to ship and retain them.

## Building the image yourself

```bash
docker build -t titerlane-biologics-backend:local .
```

Then set `TITERLANE_IMAGE=titerlane-biologics-backend` and `TITERLANE_VERSION=local` in
`deploy/.env`. Under the AGPL-3.0, if you modify the server and let users interact with it
over a network, you must offer them its source code.
