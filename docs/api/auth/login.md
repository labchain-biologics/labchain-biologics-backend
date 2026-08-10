# POST /api/v1/auth/login

Authenticate with email/password, Google ID token, or OAuth2 form. Returns a JWT access token.

| | |
| --- | --- |
| Auth | Workspace header only |
| Role | — |
| Success | `200 OK` |

!!! note "Workspace"
    Send `X-LabChain-Workspace` for audit scoping (login is audited).

## Request model

### Headers

| Header | Required | Description |
| --- | --- | --- |
| `X-LabChain-Workspace` | yes | Workspace id |
| `Content-Type` | yes | `application/json` or form |

### Query

| Param | Type | Description |
| --- | --- | --- |
| `provider` | `string?` | Set to `google` for Google ID token login |

### Body — password (`LoginRequest`)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `email` | `string` (email) | yes | |
| `password` | `string` | yes | 8–128 chars |

### Body — Google (`?provider=google`, `GoogleLoginRequest`)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `idToken` | `string` | yes | Google OAuth ID token |

### Body — OAuth2 form (Swagger)

`application/x-www-form-urlencoded` with `username` + `password`.

## Response model (`Token`)

| Field | Type | Description |
| --- | --- | --- |
| `accessToken` | `string` | JWT |
| `tokenType` | `string` | `"bearer"` |
| `expiresIn` | `int` | Seconds until expiry |

## Example

```bash
curl -s -X POST 'http://localhost:8000/api/v1/auth/login' \
  -H 'Content-Type: application/json' \
  -H 'X-LabChain-Workspace: demo' \
  -d '{
    "email": "tech@labchain.example",
    "password": "changeme123"
  }'
```

```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "tokenType": "bearer",
  "expiresIn": 28800
}
```
