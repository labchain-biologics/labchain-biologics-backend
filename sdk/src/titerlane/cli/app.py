"""
``titerlane``: the Titerlane Biologics API from a shell.

Configuration comes from ``TITERLANE_URL``, ``TITERLANE_TOKEN`` and ``TITERLANE_WORKSPACE`` (or
``--url`` / ``--workspace``). The token is deliberately not a command-line option: arguments
end up in shell history and process listings.

Exit status: 0 on success, 1 when the API, the network or a check (MD5, run outcome) fails,
2 on a usage error.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.table import Table

from titerlane._version import __version__
from titerlane.client import Client
from titerlane.errors import TiterlaneError
from titerlane.models import (
    JobStatus,
    OmicsModality,
    OutputFileType,
    QcStatus,
    Role,
    Run,
    SampleAssay,
    SampleStatus,
)

# Fields never printed: signed URLs are credentials (`results url` prints one on purpose).
HIDDEN_FIELDS = {"downloadUrl", "uploadUrl"}
READ_PAIR = re.compile(r"(?:^|[._-])(R[12])(?:[._-]|$)")

stdout = Console(soft_wrap=True)
stderr = Console(stderr=True, soft_wrap=True)

app = typer.Typer(
    name="titerlane",
    help="Titerlane Biologics from the command line: samples, FASTQ, pipeline runs, results.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
token_app = typer.Typer(help="Personal access tokens.", no_args_is_help=True)
workspaces_app = typer.Typer(help="Workspaces you belong to.", no_args_is_help=True)
members_app = typer.Typer(help="Members of the current workspace.", no_args_is_help=True)
samples_app = typer.Typer(help="Samples (LIMS records).", no_args_is_help=True)
fastq_app = typer.Typer(help="FASTQ files.", no_args_is_help=True)
pipelines_app = typer.Typer(help="nf-core pipeline catalog.", no_args_is_help=True)
runs_app = typer.Typer(help="Pipeline runs.", no_args_is_help=True)
results_app = typer.Typer(help="Pipeline outputs.", no_args_is_help=True)
for sub_app, name in (
    (token_app, "token"),
    (workspaces_app, "workspaces"),
    (members_app, "members"),
    (samples_app, "samples"),
    (fastq_app, "fastq"),
    (pipelines_app, "pipelines"),
    (runs_app, "runs"),
    (results_app, "results"),
):
    app.add_typer(sub_app, name=name)


@dataclass
class State:
    url: str | None
    workspace: str | None
    json: bool


@app.callback()
def configure(
    ctx: typer.Context,
    url: Annotated[
        str | None,
        typer.Option("--url", envvar="TITERLANE_URL", help="Server root, without /api/v1."),
    ] = None,
    workspace: Annotated[
        str | None,
        typer.Option("--workspace", "-w", envvar="TITERLANE_WORKSPACE", help="Workspace slug."),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print JSON (API field names) instead of tables.")
    ] = False,
) -> None:
    """Credentials: set TITERLANE_TOKEN to a personal access token (`titerlane token create`)."""
    ctx.obj = State(url=url, workspace=workspace, json=as_json)


# --- Plumbing ------------------------------------------------------------------------------


def _state(ctx: typer.Context) -> State:
    state = ctx.find_root().obj
    assert isinstance(state, State)
    return state


@contextmanager
def _failures() -> Iterator[None]:
    """SDK and validation errors become one ``error:`` line on stderr and exit status 1."""
    try:
        yield
    except TiterlaneError as exc:
        stderr.print(f"[red]error:[/red] {exc}", highlight=False, markup=True)
        raise typer.Exit(1) from None
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        stderr.print(f"[red]error:[/red] invalid argument: {problems}", highlight=False)
        raise typer.Exit(1) from None


@contextmanager
def connect(ctx: typer.Context, *, workspace: str | None = None) -> Iterator[Client]:
    state = _state(ctx)
    with _failures(), Client(state.url, workspace=workspace or state.workspace) as client:
        yield client


def _dump(item: Any) -> Any:
    if isinstance(item, BaseModel):
        data = item.model_dump(mode="json", by_alias=True)
        return {key: value for key, value in data.items() if key not in HIDDEN_FIELDS}
    return item


Column = tuple[str, Callable[[Any], Any]]


def emit(ctx: typer.Context, data: Any, columns: Sequence[Column] | None = None) -> None:
    """JSON with ``--json``; otherwise a table (lists) or field list (one object)."""
    if _state(ctx).json:
        payload = [_dump(item) for item in data] if isinstance(data, list) else _dump(data)
        stdout.print_json(json.dumps(payload))
        return
    if isinstance(data, list):
        assert columns is not None
        table = Table(*(header for header, _ in columns), box=None, pad_edge=False)
        for item in data:
            table.add_row(*(_text(getter(item)) for _, getter in columns))
        stdout.print(table)
        return
    for key, value in _dump(data).items():
        stdout.print(f"[bold]{key}[/bold]: {_text(value)}", highlight=False)


def _text(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(getattr(value, "value", value))


def _short(value: Any) -> str:
    return str(value)[:8]


# --- Top-level commands --------------------------------------------------------------------


@app.command()
def version() -> None:
    """Print the SDK version."""
    stdout.print(__version__, highlight=False)


@app.command()
def health(ctx: typer.Context) -> None:
    """Check that the server answers (no credentials needed)."""
    with connect(ctx) as client:
        emit(ctx, client.health())


@app.command()
def whoami(ctx: typer.Context) -> None:
    """The current user and their role in each workspace."""
    with connect(ctx) as client:
        me = client.auth.me()
    if _state(ctx).json:
        emit(ctx, me)
        return
    stdout.print(f"{me.full_name} <{me.email}>", highlight=False)
    emit(ctx, me.memberships, [("WORKSPACE", lambda m: m.slug), ("ROLE", lambda m: m.role)])


# --- Tokens --------------------------------------------------------------------------------

TOKEN_COLUMNS: list[Column] = [
    ("ID", lambda t: t.id),
    ("NAME", lambda t: t.name),
    ("PREFIX", lambda t: t.token_prefix),
    ("EXPIRES", lambda t: t.expires_at.date()),
    ("LAST USED", lambda t: t.last_used_at),
    ("REVOKED", lambda t: t.revoked_at),
]


@token_app.command("create")
def token_create(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="What the token is for.")],
    email: Annotated[
        str | None, typer.Option(help="Your account e-mail (prompted when not given).")
    ] = None,
    expires_in_days: Annotated[int | None, typer.Option(min=1)] = None,
) -> None:
    """
    Sign in with your password and issue a personal access token. The secret is printed once
    on stdout; store it (e.g. as TITERLANE_TOKEN in a secret manager).

    The password is always prompted (hidden), never an option, so it stays out of shell
    history. Prompts go to stderr: `export TITERLANE_TOKEN=$(titerlane token create ci)` works.
    """
    state = _state(ctx)
    email = email or typer.prompt("E-mail", err=True)
    password = typer.prompt("Password", hide_input=True, err=True)
    with (
        _failures(),
        Client.login(email, password, base_url=state.url) as session,
    ):
        created = session.auth.tokens.create(name, expires_in_days=expires_in_days)
    if state.json:
        stdout.print_json(json.dumps(created.model_dump(mode="json", by_alias=True)))
        return
    stderr.print(
        f"Token {created.token_prefix}... expires {created.expires_at.date()}. "
        "It is shown only now:",
        highlight=False,
    )
    print(created.token)


@token_app.command("list")
def token_list(ctx: typer.Context) -> None:
    """Your tokens, including revoked and expired ones (never the secret)."""
    with connect(ctx) as client:
        emit(ctx, client.auth.tokens.list(), TOKEN_COLUMNS)


@token_app.command("revoke")
def token_revoke(ctx: typer.Context, token_id: str) -> None:
    """Revoke a token. It stops working immediately."""
    with connect(ctx) as client:
        emit(ctx, client.auth.tokens.revoke(token_id))


# --- Workspaces and members ----------------------------------------------------------------


@workspaces_app.command("list")
def workspaces_list(ctx: typer.Context) -> None:
    with connect(ctx) as client:
        workspaces = client.workspaces.list()
    emit(
        ctx,
        workspaces,
        [("SLUG", lambda w: w.slug), ("NAME", lambda w: w.name), ("ROLE", lambda w: w.role)],
    )


@workspaces_app.command("create")
def workspaces_create(ctx: typer.Context, slug: str, name: str) -> None:
    """Create a workspace; you become its bioinformatics_lead."""
    with connect(ctx) as client:
        emit(ctx, client.workspaces.create(slug, name))


MEMBER_COLUMNS: list[Column] = [
    ("USER ID", lambda m: m.user_id),
    ("EMAIL", lambda m: m.email),
    ("NAME", lambda m: m.full_name),
    ("ROLE", lambda m: m.role),
    ("ACTIVE", lambda m: m.is_active),
]


@members_app.command("list")
def members_list(ctx: typer.Context) -> None:
    with connect(ctx) as client:
        emit(ctx, client.members.list(), MEMBER_COLUMNS)


@members_app.command("add")
def members_add(
    ctx: typer.Context,
    email: str,
    role: Role = Role.lab_technician,
) -> None:
    """Add an existing user to the workspace (bioinformatics_lead only)."""
    with connect(ctx) as client:
        emit(ctx, client.members.add(email, role))


@members_app.command("set-role")
def members_set_role(ctx: typer.Context, user_id: str, role: Role) -> None:
    """Change a member's role (bioinformatics_lead only)."""
    with connect(ctx) as client:
        emit(ctx, client.members.change_role(user_id, role))


@members_app.command("remove")
def members_remove(ctx: typer.Context, user_id: str) -> None:
    """Remove a member (bioinformatics_lead only)."""
    with connect(ctx) as client:
        client.members.remove(user_id)


# --- Samples -------------------------------------------------------------------------------

SAMPLE_COLUMNS: list[Column] = [
    ("ID", lambda s: s.id),
    ("CODE", lambda s: s.sample_code),
    ("MODALITY", lambda s: s.modality),
    ("ASSAY", lambda s: s.assay),
    ("STATUS", lambda s: s.status),
    ("QC", lambda s: s.qc_status),
    ("CREATED", lambda s: s.created_at.date()),
]

AllOption = Annotated[bool, typer.Option("--all", help="Every page, not just the first.")]


@samples_app.command("list")
def samples_list(
    ctx: typer.Context,
    status: SampleStatus | None = None,
    modality: OmicsModality | None = None,
    assay: SampleAssay | None = None,
    qc_status: Annotated[QcStatus | None, typer.Option("--qc-status")] = None,
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 100,
    every: AllOption = False,
) -> None:
    """Samples, newest first."""
    filters: dict[str, Any] = {
        "status": status,
        "modality": modality,
        "assay": assay,
        "qc_status": qc_status,
    }
    with connect(ctx) as client:
        samples = (
            list(client.samples.iter(**filters))
            if every
            else client.samples.list(**filters, limit=limit)
        )
    emit(ctx, samples, SAMPLE_COLUMNS)


@samples_app.command("get")
def samples_get(ctx: typer.Context, sample_id: str) -> None:
    with connect(ctx) as client:
        emit(ctx, client.samples.get(sample_id))


@samples_app.command("import")
def samples_import(
    ctx: typer.Context,
    csv_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Import samples from a UTF-8 CSV (one column per sample field, e.g. sampleCode)."""
    with connect(ctx) as client:
        result = client.samples.import_csv(csv_path)
    if _state(ctx).json:
        emit(ctx, result)
        return
    stdout.print(f"created {result.created}, skipped {result.skipped}", highlight=False)
    for error in result.errors:
        stderr.print(f"  {error}", highlight=False)


# --- FASTQ ---------------------------------------------------------------------------------

FASTQ_COLUMNS: list[Column] = [
    ("ID", lambda f: f.id),
    ("FILE", lambda f: f.filename),
    ("PAIR", lambda f: f.read_pair),
    ("SAMPLE", lambda f: _short(f.sample_id) if f.sample_id else None),
    ("SIZE", lambda f: f.size_bytes),
    ("MD5", lambda f: f.computed_md5 or f.expected_md5),
    ("STATUS", lambda f: f.verification_status),
]


def infer_read_pair(path: Path) -> str | None:
    """``R1`` / ``R2`` from Illumina-style names such as ``S1_L001_R1_001.fastq.gz``."""
    match = READ_PAIR.search(path.name)
    return match.group(1) if match else None


@fastq_app.command("upload")
def fastq_upload(
    ctx: typer.Context,
    files: Annotated[
        list[Path], typer.Argument(exists=True, dir_okay=False, readable=True, help="*.fastq.gz")
    ],
    sample: Annotated[str | None, typer.Option(help="Sample ID to attach the files to.")] = None,
    sequencing_run: Annotated[str | None, typer.Option("--sequencing-run")] = None,
    read_pair: Annotated[
        str | None,
        typer.Option(help="R1 or R2. Default: read from each file name (_R1_, _R2_)."),
    ] = None,
    expected_md5: Annotated[
        str | None, typer.Option(help="Provider checksum; only with a single file.")
    ] = None,
) -> None:
    """Upload gzipped FASTQ files: local MD5, upload to object storage, server-side check."""
    if expected_md5 and len(files) > 1:
        raise typer.BadParameter("--expected-md5 applies to a single file", param_hint="files")
    uploaded = []
    with connect(ctx) as client:
        for path in files:
            fastq = client.fastq.upload(
                path,
                sample_id=sample,
                sequencing_run_id=sequencing_run,
                read_pair=read_pair or infer_read_pair(path),
                expected_md5=expected_md5,
            )
            if not _state(ctx).json:
                stderr.print(f"verified {path.name}", highlight=False)
            uploaded.append(fastq)
    emit(ctx, uploaded, FASTQ_COLUMNS)


@fastq_app.command("list")
def fastq_list(
    ctx: typer.Context,
    sample: str | None = None,
    sequencing_run: Annotated[str | None, typer.Option("--sequencing-run")] = None,
) -> None:
    with connect(ctx) as client:
        files = list(client.fastq.iter(sample_id=sample, sequencing_run_id=sequencing_run))
    emit(ctx, files, FASTQ_COLUMNS)


# --- Pipelines and runs --------------------------------------------------------------------


@pipelines_app.command("list")
def pipelines_list(ctx: typer.Context) -> None:
    with connect(ctx) as client:
        pipelines = client.pipelines.list()
    emit(
        ctx,
        pipelines,
        [
            ("ID", lambda p: p.id),
            ("NAME", lambda p: p.name),
            ("DEFAULT", lambda p: p.version),
            ("VERSIONS", lambda p: ", ".join(p.versions)),
            ("ASSAYS", lambda p: ", ".join(a.value for a in p.assays)),
        ],
    )


RUN_COLUMNS: list[Column] = [
    ("ID", lambda r: r.id),
    ("PIPELINE", lambda r: f"{r.pipeline_id} {r.pipeline_version}"),
    ("STATUS", lambda r: r.status),
    ("SUBMITTED", lambda r: r.execution_submitted),
    ("SAMPLES", lambda r: len(r.sample_ids)),
    ("CREATED", lambda r: r.created_at.replace(microsecond=0)),
]


def parse_param(raw: str) -> tuple[str, Any]:
    """``key=value``; the value is read as JSON when it parses (3, true, [..]), else a string."""
    key, sep, value = raw.partition("=")
    if not sep or not key:
        raise typer.BadParameter(f"expected key=value, got {raw!r}", param_hint="--param")
    try:
        return key, json.loads(value)
    except ValueError:
        return key, value


def _warn_if_not_submitted(run: Run) -> None:
    if not run.execution_submitted:
        stderr.print(
            f"[yellow]warning:[/yellow] run {run.id} was recorded but not submitted: pipeline "
            "execution is disabled on this server, so it will stay pending.",
            highlight=False,
        )


def _follow(client: Client, run_id: str) -> None:
    for event in client.runs.stream_logs(run_id):
        if event.kind == "log":
            print(event.data, flush=True)
        elif event.kind == "status":
            stderr.print(f"status: {event.data}", highlight=False)


@runs_app.command("launch")
def runs_launch(
    ctx: typer.Context,
    pipeline: Annotated[
        str, typer.Argument(help="Pipeline ID, e.g. rnaseq (see `pipelines list`).")
    ],
    samples: Annotated[list[str], typer.Option("--sample", "-s", help="Sample ID (repeat).")],
    pipeline_version: Annotated[str, typer.Option("--version")] = "latest",
    sequencing_run: Annotated[str | None, typer.Option("--sequencing-run")] = None,
    params: Annotated[
        list[str] | None, typer.Option("--param", "-p", help="Pipeline parameter key=value.")
    ] = None,
    params_file: Annotated[
        Path | None,
        typer.Option(exists=True, dir_okay=False, help="JSON object of pipeline parameters."),
    ] = None,
    wait: Annotated[bool, typer.Option(help="Wait for the run to finish.")] = False,
    follow: Annotated[bool, typer.Option(help="Stream the run log until it ends.")] = False,
) -> None:
    """Launch an nf-core pipeline (bioinformatics_lead only)."""
    parameters: dict[str, Any] = {}
    if params_file is not None:
        loaded = json.loads(params_file.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise typer.BadParameter("must contain a JSON object", param_hint="--params-file")
        parameters.update(loaded)
    parameters.update(parse_param(raw) for raw in params or [])
    with connect(ctx) as client:
        run = client.runs.launch(
            pipeline,
            sample_ids=samples,
            pipeline_version=pipeline_version,
            sequencing_run_id=sequencing_run,
            parameters=parameters,
        )
        _warn_if_not_submitted(run)
        if follow and run.execution_submitted:
            _follow(client, str(run.id))
        if wait:
            run = client.runs.wait(run.id)
    emit(ctx, run)


@runs_app.command("list")
def runs_list(
    ctx: typer.Context,
    status: JobStatus | None = None,
    sample: str | None = None,
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 50,
    every: AllOption = False,
) -> None:
    with connect(ctx) as client:
        runs = (
            list(client.runs.iter(status=status, sample_id=sample))
            if every
            else client.runs.list(status=status, sample_id=sample, limit=limit)
        )
    emit(ctx, runs, RUN_COLUMNS)


@runs_app.command("get")
def runs_get(ctx: typer.Context, run_id: str) -> None:
    with connect(ctx) as client:
        emit(ctx, client.runs.get(run_id))


@runs_app.command("wait")
def runs_wait(
    ctx: typer.Context,
    run_id: str,
    timeout: Annotated[float | None, typer.Option(help="Give up after this many seconds.")] = None,
    poll_interval: Annotated[float, typer.Option(min=0.1)] = 15.0,
) -> None:
    """Wait until the run succeeds (exit 0), or fails / is cancelled / times out (exit 1)."""
    with connect(ctx) as client:
        run = client.runs.wait(run_id, timeout=timeout, poll_interval=poll_interval)
    emit(ctx, run)


@runs_app.command("logs")
def runs_logs(
    ctx: typer.Context,
    run_id: str,
    follow: Annotated[bool, typer.Option("--follow", "-f", help="Stream until the run ends.")] = (
        False
    ),
    after: Annotated[int, typer.Option(help="Only lines after this index.")] = -1,
) -> None:
    """Print the run log."""
    with connect(ctx) as client:
        if follow:
            _follow(client, run_id)
            return
        lines = client.runs.logs(run_id, after=after)
    if _state(ctx).json:
        emit(ctx, lines)
        return
    for line in lines:
        print(line.message)


# --- Results -------------------------------------------------------------------------------

RESULT_COLUMNS: list[Column] = [
    ("ID", lambda r: r.id),
    ("TYPE", lambda r: r.file_type),
    ("FILE", lambda r: r.filename),
    ("SIZE", lambda r: r.size_bytes),
    ("SAMPLE", lambda r: _short(r.sample_id) if r.sample_id else None),
]


@results_app.command("list")
def results_list(
    ctx: typer.Context,
    run: Annotated[str | None, typer.Option(help="Only this run's outputs.")] = None,
    file_type: Annotated[OutputFileType | None, typer.Option("--type")] = None,
) -> None:
    with connect(ctx) as client:
        outputs = (
            client.results.for_run(run)
            if run and file_type is None
            else client.results.list(run_id=run, file_type=file_type)
        )
    emit(ctx, outputs, RESULT_COLUMNS)


@results_app.command("download")
def results_download(
    ctx: typer.Context,
    output_ids: Annotated[list[str] | None, typer.Argument(help="Output IDs.")] = None,
    run: Annotated[str | None, typer.Option(help="Download every output of this run.")] = None,
    dest: Annotated[
        Path, typer.Option(file_okay=False, help="Directory to save into (created if needed).")
    ] = Path("."),
) -> None:
    """Download outputs, MD5-checked, into a directory."""
    if not output_ids and not run:
        raise typer.BadParameter("give output IDs or --run", param_hint="output_ids")
    dest.mkdir(parents=True, exist_ok=True)
    with connect(ctx) as client:
        ids: Iterable[str] = output_ids or [
            str(output.id) for output in client.results.for_run(run or "")
        ]
        paths = []
        for output_id in ids:
            path = client.results.download(output_id, dest)
            stderr.print(f"saved {path}", highlight=False)
            paths.append(str(path))
    if _state(ctx).json:
        emit(ctx, paths)


@results_app.command("url")
def results_url(ctx: typer.Context, output_id: str) -> None:
    """Print a short-lived signed download URL. It is a credential until it expires."""
    with connect(ctx) as client:
        link = client.results.download_url(output_id)
    print(link.download_url)
