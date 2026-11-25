# Run logs and Nextflow events

## GET /api/v1/runs/{run_id}/logs

The run log as JSON, for clients that poll instead of using the
[SSE stream](logs-stream.md).

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `lab_technician` or `bioinformatics_lead` |
| Success | `200 OK` |

| Query | Type | Description |
| --- | --- | --- |
| `after` | `int` | Only lines with `index` greater than this (default `-1`: all) |

Response: `RunLogLine[]` with `index` (cursor), `timestamp` and `message`.

## POST /api/v1/runs/{run_id}/events

Callback that Nextflow calls with `-with-weblog`. Not for API clients.

| | |
| --- | --- |
| Auth | `token` query parameter: per-run HMAC derived from `SECRET_KEY` |
| Success | `204 No Content` |

The launch passes `-with-weblog <PUBLIC_API_URL>/api/v1/runs/<id>/events?token=<token>` to
Nextflow only when `PUBLIC_API_URL` is set (the URL Nextflow can reach). The token is never
written to the run log. A wrong token gets `404`.

| Event | Effect |
| --- | --- |
| `started` | Status `running`, `startedAt` set |
| `process_submitted` / `process_started` / `process_completed` | Log line, `progress` counters and `currentProcess` |
| `error` | Log line, `progress.errorMessage` |
| `completed` | Status `succeeded` or `failed` (`metadata.workflow.success`), outputs registered, samples `completed` on success |

Events for a finished run are ignored, so retries and late events are harmless. Status
changes are written to the audit trail with no user actor.
