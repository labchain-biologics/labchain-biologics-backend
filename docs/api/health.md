# GET /health

Liveness probe for the API process. No authentication required.

| | |
| --- | --- |
| Auth | None |
| Role | — |
| Success | `200 OK` |

## Request model

No body, path parameters, or query parameters.

## Response model

| Field | Type | Description |
| --- | --- | --- |
| `status` | `string` | Always `"ok"` when healthy |
| `service` | `string` | Application name |
| `environment` | `string` | `APP_ENV` value |

## Example

```bash
curl -s http://localhost:8000/health
```

```json
{
  "status": "ok",
  "service": "Titerlane Biologics",
  "environment": "local"
}
```
