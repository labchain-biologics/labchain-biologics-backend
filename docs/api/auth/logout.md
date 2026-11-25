# POST /api/v1/auth/logout

Record a logout audit event. Clients should discard the JWT locally (stateless tokens).

| | |
| --- | --- |
| Auth | Bearer |
| Role | Any authenticated user |
| Success | `200 OK` |

## Request model

No body.

### Headers

| Header | Required |
| --- | --- |
| `Authorization: Bearer <token>` | yes |

## Response model (`LogoutResponse`)

| Field | Type | Description |
| --- | --- | --- |
| `detail` | `string` | `"Successfully logged out"` |

## Example

```bash
curl -s -X POST 'http://localhost:8000/api/v1/auth/logout' \
  -H 'Authorization: Bearer <access_token>'
```

```json
{
  "detail": "Successfully logged out"
}
```
