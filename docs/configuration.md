# Configuration

See [`.env.example`](https://github.com/titerlane-biologics/titerlane-biologics-backend/blob/main/.env.example). Important variables:

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | JWT HS256 secret (≥ 32 chars) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Lifetime of login JWTs (default 60) |
| `API_TOKEN_DEFAULT_LIFETIME_DAYS` | Lifetime of a personal access token when the request names none (default 90) |
| `API_TOKEN_MAX_LIFETIME_DAYS` | Longest lifetime a personal access token may request (default 365) |
| `DATABASE_URL` | Async Postgres URL (`postgresql+asyncpg://…`) |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `SECRETS_DIR` | Directory of secret files, one per setting named after it (`secret_key`, `database_url`, ...). Environment variables take precedence. `deploy/compose.yaml` sets `/run/secrets` |
| `S3_BUCKET` | Bucket for FASTQ uploads and run outputs |
| `S3_ENDPOINT_URL` | LocalStack (`http://localhost:4566`), an S3-compatible endpoint, or empty for AWS S3 (the image default) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Storage and Batch credentials. Unset: the standard AWS credential chain (IAM role, `AWS_PROFILE`, ...) |
| `AWS_REGION` | AWS region (default `us-east-1`) |
| `AWS_BATCH_ENABLED` | Submit runs to AWS Batch. `false`: runs are recorded as `pending` and not executed |
| `AWS_BATCH_JOB_QUEUE` / `AWS_BATCH_JOB_DEFINITION` | Batch queue and job definition of the Nextflow head job |
| `NEXTFLOW_WORK_DIR` | Nextflow work directory root (`s3://…`) |
| `NEXTFLOW_PROFILE` | `-profile` passed to Nextflow (default `docker`) |
| `NEXTFLOW_CONFIG_URI` | Optional extra Nextflow config passed with `-c` (e.g. AWS Batch executor settings) |
| `PUBLIC_API_URL` | URL Nextflow can reach to post weblog events; unset disables `-with-weblog` |
| `RUN_MONITOR_INTERVAL_SECONDS` | AWS Batch status polling interval (default 30, min 5) |
| `WORKSPACE_CREATION_ENABLED` | Let any authenticated user create a workspace (default `true`) |
| `BOOTSTRAP_REGISTRATION_ENABLED` | Enable `/auth/register` outside production (default `false`) |
| `GOOGLE_CLIENT_ID` | Audience for Google ID token login (optional) |
| `FORWARDED_ALLOW_IPS` | Container image only (Uvicorn): proxy IPs trusted for `X-Forwarded-*` (default `127.0.0.1`) |

For a production deployment, see [Self-hosting](self-hosting.md).

## Object storage CORS

Browsers upload FASTQ files straight to S3 with presigned URLs, so the bucket CORS policy
must allow the web origins (`PUT`, `GET`, `HEAD`). With LocalStack (`S3_ENDPOINT_URL` set)
the API applies `CORS_ORIGINS` to the bucket at startup; this also applies to any
S3-compatible endpoint. On AWS, configure it in your infrastructure.

!!! warning "Secrets"
    Never commit `.env` or real credentials. Use `.env.example` as the template only.
