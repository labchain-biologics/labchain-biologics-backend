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
| `S3_ENDPOINT_URL` | LocalStack (`http://localhost:4566`) or empty for real AWS |
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

## Object storage CORS

Browsers upload FASTQ files straight to S3 with presigned URLs, so the bucket CORS policy
must allow the web origins (`PUT`, `GET`, `HEAD`). With LocalStack (`S3_ENDPOINT_URL` set)
the API applies `CORS_ORIGINS` to the bucket at startup. On AWS, configure it in your
infrastructure.

!!! warning "Secrets"
    Never commit `.env` or real credentials. Use `.env.example` as the template only.
