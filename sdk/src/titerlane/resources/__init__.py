"""API resources, exposed as attributes of :class:`titerlane.Client`."""

from titerlane.resources.auth import Auth, Tokens
from titerlane.resources.results import Results
from titerlane.resources.runs import Pipelines, RunEvent, Runs
from titerlane.resources.samples import Samples
from titerlane.resources.sequencing import Fastq, SequencingRuns
from titerlane.resources.workspaces import Members, Workspaces

__all__ = [
    "Auth",
    "Fastq",
    "Members",
    "Pipelines",
    "Results",
    "RunEvent",
    "Runs",
    "Samples",
    "SequencingRuns",
    "Tokens",
    "Workspaces",
]
