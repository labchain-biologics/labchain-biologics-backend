# Sequencing runs

A sequencing run (flowcell) groups the FastQ files produced together. FastQ files reference it
through `sequencingRunId`.

| Method | Path | Role | Success |
| --- | --- | --- | --- |
| `GET` | `/api/v1/sequencing-runs` | any member | `200 OK` |
| `POST` | `/api/v1/sequencing-runs` | any member | `201 Created` |
| `GET` | `/api/v1/sequencing-runs/{id}` | any member | `200 OK` |

## Body (`SequencingRunCreate`)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `runName` | `string` | yes | 1–255 chars |
| `instrument` | `string?` | no | e.g. NovaSeq 6000 |
| `flowcellId` | `string?` | no | |
| `readLength` | `string?` | no | e.g. `2x150` |

## Response model (`SequencingRunRead`)

The body fields plus `id`, `workspace`, `createdBy` and `createdAt`. Creation is audited.

## Example

```bash
curl -s -X POST 'http://localhost:8000/api/v1/sequencing-runs' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-Titerlane-Workspace: helix-genomics' \
  -H 'Content-Type: application/json' \
  -d '{"runName": "RUN-2026-11-25", "flowcellId": "HVKJ2DSX5", "readLength": "2x150"}'
```
