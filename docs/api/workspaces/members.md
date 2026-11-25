# Workspace members

Manage the members of the workspace named by the `X-LabChain-Workspace` header. Every change
is written to the audit trail with before/after state.

| Method | Path | Role | Success |
| --- | --- | --- | --- |
| `GET` | `/api/v1/members` | any member | `200 OK` |
| `POST` | `/api/v1/members` | `bioinformatics_lead` | `201 Created` |
| `PATCH` | `/api/v1/members/{userId}` | `bioinformatics_lead` | `200 OK` |
| `DELETE` | `/api/v1/members/{userId}` | `bioinformatics_lead` | `204 No Content` |

All routes require:

```http
Authorization: Bearer <access_token>
X-LabChain-Workspace: <workspace-slug>
```

A workspace always keeps at least one `bioinformatics_lead`: demoting or removing the last
one returns `409`.

## Response model (`MemberRead`)

| Field | Type | Description |
| --- | --- | --- |
| `userId` | `uuid` | User id |
| `email` | `string` | Email |
| `fullName` | `string` | Display name |
| `role` | `Role` | Role in this workspace |
| `isActive` | `bool` | Account flag |
| `joinedAt` | `datetime` | Membership creation time |

## POST /api/v1/members

Add an existing user (they must already have an account) to the workspace.

| Field | Type | Required | Default |
| --- | --- | --- | --- |
| `email` | `string` (email) | yes | |
| `role` | `Role` | no | `lab_technician` |

| Status | When |
| --- | --- |
| `404` | No user with this email |
| `409` | The user is already a member |

## PATCH /api/v1/members/{userId}

| Field | Type | Required |
| --- | --- | --- |
| `role` | `Role` | yes |

## DELETE /api/v1/members/{userId}

Removes the membership. The user immediately loses access to the workspace; their past
actions stay in the audit trail.

## Example

```bash
curl -s -X POST 'http://localhost:8000/api/v1/members' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-LabChain-Workspace: helix-genomics' \
  -H 'Content-Type: application/json' \
  -d '{"email": "tech@labchain.example", "role": "lab_technician"}'
```
