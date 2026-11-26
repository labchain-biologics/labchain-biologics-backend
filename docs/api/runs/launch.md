# POST /api/v1/runs

Launch an nf-core pipeline on LIMS samples.

| | |
| --- | --- |
| Auth | Bearer + workspace |
| Role | `bioinformatics_lead` |
| Success | `201 Created` |

## What happens

1. The pipeline and revision are checked against the [catalog](../pipelines/list.md)
   (`pipelineVersion` must be one of `versions`; `latest` means the default `version`).
2. For each sample, the most recent **verified** R1 FASTQ of the workspace and the most
   recent verified R2 **of the same sequencing run** are selected. Reads from different runs
   are never paired. `sarek`, `scrnaseq`, `ampliseq` and `mag` require the R2; the others
   accept single-end reads. Each selected object must still be the version that was verified
   (same ETag), and two samples may not map to the same pipeline sample identifier
   (`RNA 1` and `RNA_1` both become `RNA_1`).
3. The pipeline's samplesheet is generated and stored at
   `s3://<bucket>/<workspace>/runs/<runId>/samplesheet.csv`.
4. The Nextflow head job is submitted to AWS Batch with:

    ```text
    nextflow run nf-core/<pipeline> -r <version> -name lc-<pipeline>-<id>
      -profile $NEXTFLOW_PROFILE -work-dir $NEXTFLOW_WORK_DIR/<workspace>/<runId>
      [-c $NEXTFLOW_CONFIG_URI] [-with-weblog <callback>]
      --input <samplesheet> --outdir s3://<bucket>/<workspace>/results/<runId> --<param> <value>…
    ```

5. Samples move to `processing`.

With `AWS_BATCH_ENABLED=false` steps 1–3 still run, but nothing is executed: the run is
recorded with status `pending`, `awsBatchJobId: null`, `executionSubmitted: false`, and a log
line saying it was not submitted. It stays `pending`: clients waiting for completion should
check `executionSubmitted` instead of polling forever. Samples keep their status.

Afterwards the run status follows Nextflow [weblog events](events.md) and/or AWS Batch
(polled every `RUN_MONITOR_INTERVAL_SECONDS`). On completion, every file under the output
directory is registered as a result (every listing page, each with an audit record), and on
success the samples move to `completed`. If storage is unavailable at that moment the run
keeps its final status, `progress.outputs` stays `pending`, and the monitor retries the
collection until it succeeds (`collected`).

### Samplesheets

| Pipeline | Columns |
| --- | --- |
| `rnaseq` | `sample,fastq_1,fastq_2,strandedness` (`auto`) |
| `sarek` | `patient,sex,status,sample,lane,fastq_1,fastq_2` (`status` 1 for `tumor` samples) |
| `scrnaseq`, `methylseq`, `viralrecon` | `sample,fastq_1,fastq_2` |
| `atacseq` | `sample,fastq_1,fastq_2,replicate` |
| `ampliseq` | `sampleID,forwardReads,reverseReads` |
| `mag` | `sample,group,short_reads_1,short_reads_2,long_reads` (`group` = `pairedGroup`) |
| `chipseq` | not supported: needs antibody/control pairing the LIMS does not record |

## Request model (`RunCreateRequest`)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `pipelineId` | `string` | yes | Catalog id (`rnaseq`, `sarek`, …) |
| `pipelineVersion` | `string` | no | default `latest` |
| `sampleIds` | `uuid[]` | yes | Samples of the current workspace |
| `sequencingRunId` | `uuid?` | no | Must belong to the current workspace |
| `parameters` | `object` | no | Merged over the catalog `defaultParams` |

`parameters` keys must be valid nf-core parameter names; values must be strings, numbers or
booleans. `input` and `outdir` are reserved. Each value is passed as a single argument (no
shell is involved).

## Errors

| Status | When |
| --- | --- |
| `404` | Unknown pipeline |
| `422` | Unknown version, unsupported pipeline, invalid parameter, sample from another workspace, sample without verified reads, missing R2 for a paired pipeline, FASTQ changed since verification, colliding sample identifiers |
| `502` | Object storage or AWS Batch unavailable |

## Response model (`PipelineJobRead`)

See [GET /runs/{id}](get.md). Fields set at launch: `status` (`submitted` or `pending`),
`awsBatchJobId`, `executionSubmitted`, `nextflowRunName`, `workDir`, `outputDir`, `samplesheetUri`.

## Example

```bash
curl -s -X POST 'http://localhost:8000/api/v1/runs' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'X-Titerlane-Workspace: helix-genomics' \
  -H 'Content-Type: application/json' \
  -d '{
    "pipelineId": "sarek",
    "pipelineVersion": "3.4.4",
    "sampleIds": ["11111111-1111-1111-1111-111111111111"],
    "parameters": {"tools": "haplotypecaller,vep"}
  }'
```
