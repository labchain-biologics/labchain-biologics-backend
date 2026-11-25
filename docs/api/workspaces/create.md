# Workspaces

A workspace is a tenant. Every sample, FASTQ file, run and result belongs to exactly one
workspace, and users only see workspaces they are a member of. These two routes are **not**
scoped by `X-LabChain-Workspace`.

## GET /api/v1/workspaces

List the active workspaces the current user belongs to, with their role in each.

| | |
| --- | --- |
| Auth | Bearer JWT |
| Role | Any authenticated user |
| Success | `200 OK` |

### Response model (`WorkspaceRead[]`)

| Field | Type | Description |
| --- | --- | --- |
| `id` | `uuid` | Workspace id |
| `slug` | `string` | Value to send as `X-LabChain-Workspace` |
| `name` | `string` | Display name |
| `role` | `Role` | Role of the current user in this workspace |
| `createdAt` | `datetime` | ISO-8601 |

## POST /api/v1/workspaces

Create a workspace. The creator becomes its first `bioinformatics_lead`. Creation and the
initial membership are both written to the audit trail.

| | |
| --- | --- |
| Auth | Bearer JWT |
| Role | Any authenticated user (when `WORKSPACE_CREATION_ENABLED=true`) |
| Success | `201 Created` |

### Body (`WorkspaceCreate`)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `slug` | `string` | yes | 1–64 chars, lowercase letters, digits and inner dashes |
| `name` | `string` | yes | 1–255 chars |

### Errors

| Status | When |
| --- | --- |
| `403` | Workspace creation is disabled on this instance |
| `409` | The slug is already taken |
| `422` | Invalid slug or name |

### Example

```bash
curl -s -X POST 'http://localhost:8000/api/v1/workspaces' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'Content-Type: application/json' \
  -d '{"slug": "helix-genomics", "name": "Helix Clinical Genomics"}'
```

```json
{
  "id": "0f8fad5b-d9cb-469f-a165-70867728950e",
  "slug": "helix-genomics",
  "name": "Helix Clinical Genomics",
  "role": "bioinformatics_lead",
  "createdAt": "2026-11-25T15:00:00Z"
}
```
