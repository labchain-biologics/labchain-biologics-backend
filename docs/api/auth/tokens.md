# /api/v1/auth/tokens

Personal access tokens (PATs) are long-lived bearer credentials for scripts, notebooks, CI
jobs and the Python SDK, where a 60-minute login JWT is impractical.

A token acts **as its owner**: it carries no role of its own, and each request still needs
`X-LabChain-Workspace` on tenant routes, where the owner's role in that workspace applies.
A deactivated user's tokens stop working.

| | |
| --- | --- |
| Auth | Bearer (login JWT or personal access token, except for creation) |
| Role | Any authenticated user, for their own tokens |
| Workspace header | Not used |

## Security model

- The secret starts with `lcb_pat_` and is returned **once**, in the creation response.
  The server stores only its SHA-256 digest and cannot show it again.
- Every token expires. The default lifetime is `API_TOKEN_DEFAULT_LIFETIME_DAYS` (90) and
  the maximum `API_TOKEN_MAX_LIFETIME_DAYS` (365); see [Configuration](../../configuration.md).
- **Creating** a token requires a login JWT. A personal access token cannot create another
  one, so a leaked token cannot outlive its own revocation.
- Revocation is a soft delete (`revokedAt`), effective immediately. Tokens are never removed.
- Creation and revocation are written to the audit trail (`entity_type = api_token`) with the
  name, prefix and dates, never the secret or its digest. Use of a token updates `lastUsedAt`
  (at most once a minute) without an audit entry.
- Another user's token answers `404`, like a token that does not exist.

Send the token like a JWT:

```http
Authorization: Bearer lcb_pat_…
```

## Response model (`ApiTokenRead`)

| Field | Type | Description |
| --- | --- | --- |
| `id` | `uuid` | Token id |
| `name` | `string` | What the token is for |
| `tokenPrefix` | `string` | First 16 characters of the secret, to tell tokens apart |
| `createdAt` | `datetime` | ISO-8601 |
| `expiresAt` | `datetime` | ISO-8601 |
| `lastUsedAt` | `datetime \| null` | Last authenticated request (one-minute resolution) |
| `revokedAt` | `datetime \| null` | Set once revoked |

## POST /api/v1/auth/tokens

Create a token. **Requires a login JWT.** Success: `201 Created`.

### Request model (`ApiTokenCreate`)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | `string` (1–100, trimmed) | yes | What the token is for |
| `expiresInDays` | `int ≥ 1` | no | Lifetime; default and maximum set by the server |

### Response model (`ApiTokenCreated`)

`ApiTokenRead` plus:

| Field | Type | Description |
| --- | --- | --- |
| `token` | `string` | The secret. Store it now: it is not returned again |

### Errors

| Status | When |
| --- | --- |
| `401` | Missing or invalid credentials |
| `403` | Called with a personal access token |
| `422` | Blank or too long `name`, `expiresInDays` < 1 or above the server maximum |

### Example

```bash
curl -s -X POST 'http://localhost:8000/api/v1/auth/tokens' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'Content-Type: application/json' \
  -d '{"name": "analysis notebook", "expiresInDays": 30}'
```

```json
{
  "id": "3f2b8c1e-5d4a-4c6b-9e1f-2a7d8c9b0e11",
  "name": "analysis notebook",
  "tokenPrefix": "lcb_pat_Xy3kQ9vL",
  "createdAt": "2026-11-25T19:00:00Z",
  "expiresAt": "2026-12-25T19:00:00Z",
  "lastUsedAt": null,
  "revokedAt": null,
  "token": "lcb_pat_Xy3kQ9vL…"
}
```

## GET /api/v1/auth/tokens

The current user's tokens, newest first, including revoked and expired ones. The secret is
never included. Success: `200 OK` with `ApiTokenRead[]`.

```bash
curl -s 'http://localhost:8000/api/v1/auth/tokens' \
  -H 'Authorization: Bearer <access_token>'
```

## DELETE /api/v1/auth/tokens/{token_id}

Revoke a token. It stops working immediately. A token may revoke itself. Success: `200 OK`
with the revoked `ApiTokenRead`.

| Status | When |
| --- | --- |
| `404` | Unknown token, or a token of another user |
| `409` | Already revoked |

```bash
curl -s -X DELETE 'http://localhost:8000/api/v1/auth/tokens/<token_id>' \
  -H 'Authorization: Bearer <access_token>'
```
