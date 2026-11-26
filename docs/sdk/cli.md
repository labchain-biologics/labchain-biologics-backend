# Command line

The SDK ships a `labchain` command for shell scripts, CI jobs and quick checks. It needs the
`cli` extra, which adds [Typer](https://typer.tiangolo.com/) and its dependencies (Rich for
tables):

```bash
pip install "./labchain-biologics-backend/sdk[cli]"   # from a checkout, until the PyPI release
labchain --help
```

Without the extra, `labchain` prints the install command instead of a traceback.

## Configure

The command reads the same environment variables as the Python client:

```bash
export LABCHAIN_URL=http://localhost:8000
export LABCHAIN_WORKSPACE=demo-lab
export LABCHAIN_TOKEN=$(labchain token create "my laptop" --email you@lab.example)
```

`--url` and `--workspace` / `-w` override the environment for one command.

!!! note "Secrets never go on the command line"
    There is no `--token` or `--password` option: arguments end up in shell history and
    process listings. The token comes from `LABCHAIN_TOKEN`, and `token create` always
    prompts for the password (hidden; prompts go to stderr, so the command substitution
    above captures only the token).

## Commands

| Command | What it does |
| --- | --- |
| `labchain version` | SDK version |
| `labchain health` | Server liveness, no credentials |
| `labchain whoami` | Current user and their role in each workspace |
| `labchain token create NAME [--email E] [--expires-in-days N]` | Sign in and issue a personal access token (printed once) |
| `labchain token list` / `token revoke ID` | Your tokens / revoke one |
| `labchain workspaces list` / `workspaces create SLUG NAME` | Your workspaces / create one |
| `labchain members list` / `add EMAIL [--role R]` / `set-role USER_ID ROLE` / `remove USER_ID` | Workspace members (changes: lead only) |
| `labchain samples list [--status] [--modality] [--assay] [--qc-status] [--limit N \| --all]` | Samples, newest first |
| `labchain samples get ID` / `samples import FILE.csv` | One sample / CSV import |
| `labchain fastq upload FILE... [--sample ID] [--sequencing-run ID] [--read-pair R1\|R2] [--expected-md5 MD5]` | Upload and verify FASTQ files |
| `labchain fastq list [--sample ID] [--sequencing-run ID]` | FASTQ files |
| `labchain pipelines list` | nf-core pipelines and their versions |
| `labchain runs launch PIPELINE -s SAMPLE... [--version V] [-p key=value...] [--params-file F] [--wait] [--follow]` | Launch a run (lead only) |
| `labchain runs list [--status] [--sample ID] [--limit N \| --all]` / `runs get ID` | Runs |
| `labchain runs wait ID [--timeout S] [--poll-interval S]` | Wait for the outcome |
| `labchain runs logs ID [--follow] [--after N]` | Run log, or live stream |
| `labchain results list [--run ID] [--type vcf\|bam\|multiqc\|other]` | Outputs |
| `labchain results download [OUTPUT_ID...] [--run ID] [--dest DIR]` | MD5-checked downloads |
| `labchain results url OUTPUT_ID` | A short-lived signed URL (a credential until it expires) |

Every command has `--help`. Enum options (`--status`, `--modality`, `--role`, ...) list their
valid values there and reject anything else before contacting the server.

### FASTQ read pairs

Without `--read-pair`, `fastq upload` reads `R1` / `R2` from Illumina-style names
(`S1_L001_R1_001.fastq.gz`, `sample.R2.fastq.gz`), so a whole directory uploads in one go:

```bash
labchain fastq upload --sample "$SAMPLE_ID" fastq/RNA-001_*.fastq.gz
```

### Pipeline parameters

`-p key=value` is repeatable. Values are read as JSON when they parse (`8`, `true`,
`["a","b"]`) and as strings otherwise. `--params-file` loads a JSON object first; `-p` values
override it.

```bash
labchain runs launch sarek -s "$SAMPLE_ID" -p tools=mutect2 -p skip_qc=true --follow
```

When pipeline execution is disabled on the server, `launch` warns that the run was recorded
but not submitted, and `--wait` fails instead of waiting forever.

## Output

Tables by default. `--json` (before the command) prints the API's JSON instead, with its
camelCase field names, for `jq` and scripts:

```bash
labchain --json samples list --qc-status pass --all | jq -r '.[].sampleCode'
```

Signed storage URLs are left out of every output except `results url`.

## Exit status

| Status | Meaning |
| --- | --- |
| `0` | Success |
| `1` | The API refused the request, the server could not be reached, a check failed (MD5 mismatch), a run failed, was cancelled, timed out or cannot execute, or an argument is invalid. One `error:` line on stderr explains it |
| `2` | Usage error (unknown option, invalid choice) |

So `labchain runs wait "$RUN_ID"` can gate a CI step on the pipeline outcome.

## Shell completion

```bash
labchain --install-completion   # bash, zsh, fish or PowerShell
```
