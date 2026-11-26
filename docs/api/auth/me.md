# GET /api/v1/auth/me

Return the authenticated user profile and the workspaces they belong to.

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

`X-Titerlane-Workspace` is not used by this route (the user is not workspace-scoped).

## Response model (`UserMe`)

| Field | Type | Description |
| --- | --- | --- |
| `id` | `uuid` | User id |
| `email` | `string` | Email |
| `fullName` | `string` | Display name |
| `isActive` | `bool` | Account flag |
| `createdAt` | `datetime` | ISO-8601 |
| `memberships` | `MembershipSummary[]` | Active workspaces, sorted by name |

### `MembershipSummary`

| Field | Type | Description |
| --- | --- | --- |
| `workspaceId` | `uuid` | Workspace id |
| `slug` | `string` | Value to send as `X-Titerlane-Workspace` |
| `name` | `string` | Display name |
| `role` | `Role` | Role **in this workspace**: `lab_technician` or `bioinformatics_lead` |

## Example

```bash
curl -s 'http://localhost:8000/api/v1/auth/me' \
  -H 'Authorization: Bearer <access_token>'
```

```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "email": "tech@titerlane.example",
  "fullName": "Alex Technician",
  "isActive": true,
  "createdAt": "2026-08-10T12:00:00Z",
  "memberships": [
    {
      "workspaceId": "0f8fad5b-d9cb-469f-a165-70867728950e",
      "slug": "helix-genomics",
      "name": "Helix Clinical Genomics",
      "role": "lab_technician"
    }
  ]
}
```
