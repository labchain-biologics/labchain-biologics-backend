# GET /api/v1/runs/{run_id}/logs/stream

Server-Sent Events (SSE) stream of run logs.

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `200 OK` (`text/event-stream`) |

## Request model

### Path

| Param | Type | Required |
| --- | --- | --- |
| `run_id` | `uuid` | yes |

No body. Use `Accept: text/event-stream` (clients usually set this automatically).

## Response model (SSE events)

Events are not a JSON schema envelope; each SSE message has:

| Field | Description |
| --- | --- |
| `event` | `log`, `status`, or `end` |
| `data` | Log line, status value, or `stream-complete` |
| `id` | Monotonic event id |

## Example

```bash
curl -N 'http://localhost:8000/api/v1/runs/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/logs/stream' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-LabChain-Workspace: demo' \
  -H 'Accept: text/event-stream'
```

```text
event: log
id: 1
data: [2026-08-10T12:00:00+00:00] Submitted Nextflow run 'RNA-001-rnaseq' for pipeline nf-core/rnaseq@3.14.0

event: log
id: 2
data: [2026-08-10T12:00:01+00:00] Executor starting Nextflow processes

event: status
id: 7
data: succeeded

event: end
id: 8
data: stream-complete
```
