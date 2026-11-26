# POST /api/v1/auth/login

Authenticate with email/password, Google ID token, or OAuth2 form. Returns a JWT access token.

| | |
| --- | --- |
| Auth | None |
| Role | — |
| Success | `200 OK` |

!!! note "Workspace"
    Login is not workspace-scoped: no `X-Titerlane-Workspace` header is needed. The login is
    audited with an empty workspace. Use [`GET /auth/me`](me.md) to list the user's workspaces.

## Request model

### Headers

| Header | Required | Description |
| --- | --- | --- |
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
  -d '{
    "email": "tech@titerlane.example",
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
