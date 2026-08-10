# GET /api/v1/auth/me

Return the authenticated user profile.

| | |
| --- | --- |
| Auth | Bearer JWT |
| Role | Any authenticated user |
| Success | `200 OK` |

## Request model

No body. Requires:

```http
Authorization: Bearer <access_token>
```

`X-LabChain-Workspace` is optional for this route (user is not workspace-scoped).

## Response model (`UserRead`)

| Field | Type | Description |
| --- | --- | --- |
| `id` | `uuid` | User id |
| `email` | `string` | Email |
| `fullName` | `string` | Display name |
| `role` | `Role` | `lab_technician` or `bioinformatics_lead` |
| `isActive` | `bool` | Account flag |
| `createdAt` | `datetime` | ISO-8601 |

## Example

```bash
curl -s 'http://localhost:8000/api/v1/auth/me' \
  -H 'Authorization: Bearer <access_token>'
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
