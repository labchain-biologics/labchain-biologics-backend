# POST /api/v1/auth/register

Bootstrap user registration for local/dev. **Disabled when `APP_ENV=production`** and
unless `BOOTSTRAP_REGISTRATION_ENABLED=true`.

The new user belongs to no workspace. They either create one with
[`POST /workspaces`](../workspaces/create.md) (and become its `bioinformatics_lead`) or are
added to an existing one by a lead with [`POST /members`](../workspaces/members.md).

| | |
| --- | --- |
| Auth | None |
| Role | — |
| Success | `201 Created` |

## Request model

### Headers

| Header | Required |
| --- | --- |
| `Content-Type: application/json` | yes |

### Query

| Param | Type | Default | Description |
| --- | --- | --- | --- |
| `fullName` | `string` | `""` | Display name (falls back to email local-part) |

### Body (`LoginRequest`)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `email` | `string` (email) | yes | |
| `password` | `string` | yes | 8–128 chars |

## Response model (`UserRead`)

Same as [GET /auth/me](me.md), without `memberships`.

## Example

```bash
curl -s -X POST 'http://localhost:8000/api/v1/auth/register?fullName=Alex%20Technician' \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "tech@titerlane.example",
    "password": "changeme123"
  }'
```

```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "email": "tech@titerlane.example",
  "fullName": "Alex Technician",
  "isActive": true,
  "createdAt": "2026-08-10T12:00:00Z"
}
```
