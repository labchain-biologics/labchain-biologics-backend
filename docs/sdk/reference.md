# Reference

Every resource is an attribute of `Client`. "Role" is what the server requires in the
client's workspace: **any** means any member (`lab_technician` or `bioinformatics_lead`),
**lead** means `bioinformatics_lead`. IDs accept a `uuid.UUID` or its string.

## Client

| Member | Description |
| --- | --- |
| `Client(base_url=None, *, token=None, workspace=None, timeout=30.0, max_retries=2, transport=None)` | See [Configure](index.md#configure) |
| `Client.login(email, password, *, base_url=None, workspace=None, ...)` | Password login (one-hour session) |
| `client.with_workspace(slug)` | Client for another workspace, same connection and credentials |
| `client.health()` | Server liveness (`dict`), no credentials needed |
| `client.base_url`, `client.workspace` | Current settings |
| `client.close()` | Close connections (also on `with` exit) |

`AsyncClient` has the same members with the same arguments, awaited; `iter` and
`stream_logs` return async iterators. See [Async client](async.md).

## auth

Not workspace-scoped. [API: /auth](../api/auth/me.md)

| Method | Returns | Route |
| --- | --- | --- |
| `auth.me()` | `User` | `GET /auth/me` |
| `auth.logout()` | `None` | `POST /auth/logout` |
| `auth.tokens.list()` | `list[ApiToken]` | `GET /auth/tokens` |
| `auth.tokens.create(name, *, expires_in_days=None)` | `ApiTokenCreated` | `POST /auth/tokens` (login session only) |
| `auth.tokens.revoke(token_id)` | `ApiToken` | `DELETE /auth/tokens/{id}` |

## workspaces and members

| Method | Returns | Route | Role |
| --- | --- | --- | --- |
| `workspaces.list()` | `list[Workspace]` | `GET /workspaces` | not scoped |
| `workspaces.create(slug, name)` | `Workspace` | `POST /workspaces` | not scoped; you become lead |
| `members.list()` | `list[Member]` | `GET /members` | any |
| `members.add(email, role="lab_technician")` | `Member` | `POST /members` | lead |
| `members.change_role(user_id, role)` | `Member` | `PATCH /members/{id}` | lead |
| `members.remove(user_id)` | `None` | `DELETE /members/{id}` | lead |

## samples

Role: any. [API: /samples](../api/samples/list.md)

| Method | Returns | Route |
| --- | --- | --- |
| `samples.list(*, modality, assay, status, qc_status, limit=100, offset=0)` | `list[Sample]` | `GET /samples` |
| `samples.iter(*, modality, assay, status, qc_status, page_size=1000)` | `Iterator[Sample]` | `GET /samples` (all pages) |
| `samples.get(sample_id)` | `Sample` | `GET /samples/{id}` |
| `samples.create(SampleCreate \| **fields)` | `Sample` | `POST /samples` |
| `samples.update(sample_id, SampleUpdate \| **fields)` | `Sample` | `PATCH /samples/{id}` (only given fields) |
| `samples.delete(sample_id)` | `None` | `DELETE /samples/{id}` (soft delete) |
| `samples.bulk_update({id: SampleUpdate \| dict})` | `list[Sample]` | `PATCH /samples/bulk` |
| `samples.bulk_delete(ids)` | `int` (deleted count) | `DELETE /samples/bulk` |
| `samples.import_csv(path)` | `SampleImportResult` | `POST /samples/import` |

## sequencing_runs

Role: any. [API: /sequencing-runs](../api/sequencing-runs/index.md)

| Method | Returns | Route |
| --- | --- | --- |
| `sequencing_runs.list(*, limit=100, offset=0)` | `list[SequencingRun]` | `GET /sequencing-runs` |
| `sequencing_runs.iter(*, page_size=1000)` | `Iterator[SequencingRun]` | all pages |
| `sequencing_runs.get(run_id)` | `SequencingRun` | `GET /sequencing-runs/{id}` |
| `sequencing_runs.create(SequencingRunCreate \| **fields)` | `SequencingRun` | `POST /sequencing-runs` |

## fastq

Role: any. [API: /fastq](../api/fastq/list.md)

| Method | Returns | Route |
| --- | --- | --- |
| `fastq.list(*, sample_id, sequencing_run_id, limit=200, offset=0)` | `list[FastqFile]` | `GET /fastq` |
| `fastq.iter(*, sample_id, sequencing_run_id, page_size=1000)` | `Iterator[FastqFile]` | all pages |
| `fastq.get(fastq_id)` | `FastqFile` | `GET /fastq/{id}` |
| `fastq.register(FastqRegisterRequest \| **fields)` | `FastqRegistration` | `POST /fastq/register` |
| `fastq.verify(fastq_id)` | `FastqVerification` | `POST /fastq/{id}/verify` |
| `fastq.upload(path, *, sample_id, sequencing_run_id, read_pair, expected_md5)` | `FastqFile` | register + upload + verify |

## pipelines

Role: any. [API: /pipelines](../api/pipelines/list.md)

| Method | Returns | Route |
| --- | --- | --- |
| `pipelines.list()` | `list[Pipeline]` | `GET /pipelines` |
| `pipelines.get(pipeline_id)` | `Pipeline` | `GET /pipelines/{id}` |

## runs

[API: /runs](../api/runs/list.md)

| Method | Returns | Route | Role |
| --- | --- | --- | --- |
| `runs.list(*, status, sample_id, limit=50, offset=0)` | `list[Run]` | `GET /runs` | any |
| `runs.iter(*, status, sample_id, page_size=1000)` | `Iterator[Run]` | all pages | any |
| `runs.get(run_id)` | `Run` | `GET /runs/{id}` | any |
| `runs.launch(pipeline_id, *, sample_ids, pipeline_version="latest", sequencing_run_id=None, parameters=None)` | `Run` | `POST /runs` | lead |
| `runs.wait(run_id, *, timeout=None, poll_interval=15.0, raise_on_failure=True)` | `Run` | polls `GET /runs/{id}` | any |
| `runs.logs(run_id, *, after=-1)` | `list[RunLogLine]` | `GET /runs/{id}/logs` | any |
| `runs.stream_logs(run_id)` | `Iterator[RunEvent]` | `GET /runs/{id}/logs/stream` | any |

`RunEvent` (importable from `labchain`) has `kind` (`"log"`, `"status"` or `"end"`), `data`
(the log line, the new status, or the final status / `run-not-found`) and `index` (log
position, for `logs(after=...)`).

## results

Role: any. [API: /results](../api/results/list.md)

| Method | Returns | Route |
| --- | --- | --- |
| `results.list(*, run_id=None, file_type=None)` | `list[ResultFile]` | `GET /results` |
| `results.for_run(run_id)` | `list[ResultFile]` | `GET /results/runs/{id}` |
| `results.download_url(output_id)` | `ResultDownload` | `GET /results/{id}/download` |
| `results.download(output_id, dest)` | `Path` | signed URL + MD5-checked download |

## Models

Response models (`labchain.models`) are Pydantic models with snake_case attributes. They
ignore unknown fields, so a newer server does not break an older SDK. Request models
(`SampleCreate`, `SampleUpdate`, `SequencingRunCreate`, `FastqRegisterRequest`, ...) reject
unknown fields, so a typo fails locally instead of being silently dropped.

| Model | Main fields |
| --- | --- |
| `User` | `id`, `email`, `full_name`, `is_active`, `memberships` (`slug`, `name`, `role`) |
| `ApiToken` / `ApiTokenCreated` | `id`, `name`, `token_prefix`, `expires_at`, `last_used_at`, `revoked_at`; `token` (created only) |
| `Workspace` | `id`, `slug`, `name`, `role`, `created_at` |
| `Member` | `user_id`, `email`, `full_name`, `role`, `is_active`, `joined_at` |
| `Sample` | `id`, `sample_code`, `modality`, `assay`, `sample_type`, `status`, `qc_status`, lab fields, `metadata` |
| `SampleImportResult` | `created`, `skipped`, `errors`, `samples` |
| `SequencingRun` | `id`, `run_name`, `instrument`, `flowcell_id`, `read_length` |
| `FastqFile` | `id`, `filename`, `s3_key`, `size_bytes`, `expected_md5`, `computed_md5`, `verification_status`, `sample_id`, `read_pair` |
| `Pipeline` | `id`, `name`, `version`, `versions`, `assays`, `default_params` |
| `Run` | `id`, `pipeline_id`, `pipeline_version`, `status`, `execution_submitted`, `sample_ids`, `parameters`, `progress`, `output_files`, timestamps |
| `RunLogLine` | `index`, `timestamp`, `message` |
| `ResultFile` | `id`, `file_type`, `filename`, `size_bytes`, `md5`, `sample_id` |
| `ResultDownload` | `id`, `filename`, `download_url`, `expires_in`, `md5` |

Signed URLs (`upload_url`, `download_url`) and token secrets are excluded from `repr()`.

## Enums

String enums (`enum.StrEnum`): pass the member or its value.

| Enum | Values |
| --- | --- |
| `Role` | `bioinformatics_lead`, `lab_technician` |
| `OmicsModality` | `genomics`, `transcriptomics`, `epigenomics`, `proteomics`, `metabolomics`, `multiomics` |
| `SampleAssay` | `wgs`, `exome`, `targeted_panel`, `bulk_rna`, `single_cell_rna`, `atac_seq`, `methylation`, `amplicon_16s`, `metagenomics` |
| `SampleType` | `tumor`, `normal`, `control`, `environmental`, `cell_line` |
| `SampleStatus` | `registered`, `fastq_received`, `processing`, `completed` |
| `QcStatus` | `pending`, `pass` (`QcStatus.pass_`), `fail`, `warn` |
| `JobStatus` | `pending`, `submitted`, `running`, `succeeded`, `failed`, `cancelled` |
| `FastqVerificationStatus` | `pending`, `verified`, `mismatch` |
| `OutputFileType` | `vcf`, `bam`, `multiqc`, `other` |

The full list of each enum is in the [API overview](../api-overview.md). The SDK's models and
enums are checked against the server's `openapi.json` in CI, so they cannot drift silently.
