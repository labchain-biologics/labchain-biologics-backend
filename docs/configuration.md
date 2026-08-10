# Configuration

See [`.env.example`](https://github.com/labchain-biologics/labchain-biologics-backend/blob/main/.env.example). Important variables:

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | JWT HS256 secret (≥ 32 chars) |
| `DATABASE_URL` | Async Postgres URL (`postgresql+asyncpg://…`) |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `S3_ENDPOINT_URL` | LocalStack (`http://localhost:4566`) or empty for real AWS |
| `AWS_BATCH_ENABLED` | `false` locally; enable in deployed environments |
| `GOOGLE_CLIENT_ID` | Audience for Google ID token login (optional) |

!!! warning "Secrets"
    Never commit `.env` or real credentials. Use `.env.example` as the template only.
