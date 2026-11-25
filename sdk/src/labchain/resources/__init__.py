"""API resources, exposed as attributes of :class:`labchain.Client`."""

from labchain.resources.auth import Auth, Tokens
from labchain.resources.results import Results
from labchain.resources.runs import Pipelines, RunEvent, Runs
from labchain.resources.samples import Samples
from labchain.resources.sequencing import Fastq, SequencingRuns
from labchain.resources.workspaces import Members, Workspaces

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
