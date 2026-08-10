# POST /api/v1/auth/register

Bootstrap user registration for local/dev. **Disabled when `APP_ENV=production`.**

| | |
| --- | --- |
| Auth | Workspace header |
| Role | — |
| Success | `201 Created` |

## Request model

### Headers

| Header | Required |
| --- | --- |
| `X-LabChain-Workspace` | yes |
| `Content-Type: application/json` | yes |

### Query

| Param | Type | Default | Description |
| --- | --- | --- | --- |
| `fullName` | `string` | `""` | Display name (falls back to email local-part) |
| `role` | `Role` | `lab_technician` | Initial role |

### Body (`LoginRequest`)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `email` | `string` (email) | yes | |
| `password` | `string` | yes | 8–128 chars |

## Response model (`UserRead`)

Same as [GET /auth/me](me.md).

## Example

```bash
curl -s -X POST 'http://localhost:8000/api/v1/auth/register?fullName=Alex%20Technician&role=lab_technician' \
  -H 'Content-Type: application/json' \
  -H 'X-LabChain-Workspace: demo' \
  -d '{
    "email": "tech@labchain.example",
    "password": "changeme123"
  }'
```

```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "email": "tech@labchain.example",
  "fullName": "Alex Technician",
  "role": "lab_technician",
  "isActive": true,
  "createdAt": "2026-08-10T12:00:00Z"
}
```
