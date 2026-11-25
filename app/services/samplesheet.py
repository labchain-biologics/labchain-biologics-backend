"""Build nf-core samplesheets from LIMS samples and their verified FASTQ files.

Each nf-core pipeline expects its own CSV columns (see each pipeline's ``docs/usage.md``).
Only verified FASTQ files are used, so a run never starts on reads whose integrity was not
checked.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import FastqFile, FastqVerificationStatus
from app.models.sample import Sample, SampleType


@dataclass(frozen=True, slots=True)
class SamplesheetEntry:
    sample: Sample
    fastq_1: str
    fastq_2: str | None
    # FASTQ records used, so callers can check the stored objects are still the verified ones.
    files: tuple[FastqFile, ...] = ()


class UnsupportedPipelineError(ValueError):
    """The pipeline needs metadata the LIMS does not hold, so no samplesheet can be built."""


class DuplicateSampleIdentifierError(ValueError):
    """Two samples map to the same pipeline sample identifier after normalization."""


def _safe_name(value: str) -> str:
    """nf-core sample names: no spaces or special characters."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def _ampliseq_id(value: str) -> str:
    """ampliseq sampleID: starts with a letter, only letters, digits and underscores."""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value)
    return cleaned if cleaned[:1].isalpha() else f"S_{cleaned}"


Row = dict[str, str]
RowBuilder = Callable[[SamplesheetEntry], Row]


def _standard(e: SamplesheetEntry) -> Row:
    return {
        "sample": _safe_name(e.sample.sample_code),
        "fastq_1": e.fastq_1,
        "fastq_2": e.fastq_2 or "",
    }


def _rnaseq(e: SamplesheetEntry) -> Row:
    return {**_standard(e), "strandedness": "auto"}


def _sarek(e: SamplesheetEntry) -> Row:
    return {
        "patient": _safe_name(e.sample.patient_id or e.sample.sample_code),
        "sex": "NA",
        "status": "1" if e.sample.sample_type == SampleType.tumor else "0",
        "sample": _safe_name(e.sample.sample_code),
        "lane": "L001",
        "fastq_1": e.fastq_1,
        "fastq_2": e.fastq_2 or "",
    }


def _atacseq(e: SamplesheetEntry) -> Row:
    return {**_standard(e), "replicate": "1"}


def _ampliseq(e: SamplesheetEntry) -> Row:
    return {
        "sampleID": _ampliseq_id(e.sample.sample_code),
        "forwardReads": e.fastq_1,
        "reverseReads": e.fastq_2 or "",
    }


def _mag(e: SamplesheetEntry) -> Row:
    return {
        "sample": _safe_name(e.sample.sample_code),
        "group": _safe_name(e.sample.paired_group or "0"),
        "short_reads_1": e.fastq_1,
        "short_reads_2": e.fastq_2 or "",
        "long_reads": "",
    }


_BUILDERS: dict[str, tuple[list[str], RowBuilder]] = {
    "rnaseq": (["sample", "fastq_1", "fastq_2", "strandedness"], _rnaseq),
    "sarek": (["patient", "sex", "status", "sample", "lane", "fastq_1", "fastq_2"], _sarek),
    "scrnaseq": (["sample", "fastq_1", "fastq_2"], _standard),
    "atacseq": (["sample", "fastq_1", "fastq_2", "replicate"], _atacseq),
    "methylseq": (["sample", "fastq_1", "fastq_2"], _standard),
    "viralrecon": (["sample", "fastq_1", "fastq_2"], _standard),
    "ampliseq": (["sampleID", "forwardReads", "reverseReads"], _ampliseq),
    "mag": (["sample", "group", "short_reads_1", "short_reads_2", "long_reads"], _mag),
}


# nf-core pipelines in the catalog whose samplesheet schema requires both mates.
REQUIRES_PAIRED_READS = frozenset({"sarek", "scrnaseq", "ampliseq", "mag"})

# Column holding the sample identifier the pipeline groups reads by.
_ID_COLUMN = {"ampliseq": "sampleID"}


def supports(pipeline_id: str) -> bool:
    return pipeline_id in _BUILDERS


def build_samplesheet(pipeline_id: str, entries: Sequence[SamplesheetEntry]) -> str:
    """Render the CSV samplesheet ``pipeline_id`` expects."""
    if pipeline_id not in _BUILDERS:
        raise UnsupportedPipelineError(
            f"Samplesheet generation is not supported for nf-core/{pipeline_id} "
            "(it needs metadata the LIMS does not record, e.g. ChIP antibody/control pairs)"
        )
    columns, build = _BUILDERS[pipeline_id]
    rows = [build(entry) for entry in entries]
    id_column = _ID_COLUMN.get(pipeline_id, "sample")
    seen: dict[str, str] = {}
    for entry, row in zip(entries, rows, strict=True):
        identifier = row[id_column]
        if identifier in seen:
            raise DuplicateSampleIdentifierError(
                f"Samples '{seen[identifier]}' and '{entry.sample.sample_code}' both become "
                f"'{identifier}' in the nf-core/{pipeline_id} samplesheet; rename one of them"
            )
        seen[identifier] = entry.sample.sample_code
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def storage_prefix(workspace: str) -> str:
    """Key prefix every FASTQ object of ``workspace`` must live under."""
    return f"{workspace}/fastq/"


def _latest(files: list[FastqFile], read_pair: str) -> FastqFile | None:
    matching = [f for f in files if (f.read_pair or "").upper() == read_pair]
    return max(matching, key=lambda f: f.created_at) if matching else None


async def collect_entries(
    db: AsyncSession,
    pipeline_id: str,
    workspace: str,
    samples: Sequence[Sample],
    to_uri: Callable[[str], str],
) -> list[SamplesheetEntry]:
    """
    Pick, for each sample, its most recent verified R1 and the most recent verified R2 of the
    same sequencing run. Only FASTQ records of ``workspace`` stored under its namespace are
    considered. Raises 422 naming every sample without usable reads (R2 is required for
    pipelines in ``REQUIRES_PAIRED_READS``).
    """
    if not samples:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Select at least one sample to build the samplesheet",
        )
    result = await db.execute(
        select(FastqFile).where(
            FastqFile.workspace == workspace,
            FastqFile.sample_id.in_([s.id for s in samples]),
            FastqFile.verification_status == FastqVerificationStatus.verified,
            FastqFile.verified_etag.is_not(None),
            FastqFile.s3_key.startswith(storage_prefix(workspace), autoescape=True),
        )
    )
    by_sample: dict[object, list[FastqFile]] = {}
    for fastq in result.scalars().all():
        by_sample.setdefault(fastq.sample_id, []).append(fastq)

    paired = pipeline_id in REQUIRES_PAIRED_READS
    entries: list[SamplesheetEntry] = []
    missing_r1: list[str] = []
    missing_r2: list[str] = []
    for sample in samples:
        files = by_sample.get(sample.id, [])
        r1 = _latest(files, "R1")
        if r1 is None:
            missing_r1.append(sample.sample_code)
            continue
        # Never pair reads from different sequencing runs.
        same_run = [f for f in files if f.sequencing_run_id == r1.sequencing_run_id]
        r2 = _latest(same_run, "R2")
        if r2 is None and paired:
            missing_r2.append(sample.sample_code)
            continue
        entries.append(
            SamplesheetEntry(
                sample=sample,
                fastq_1=to_uri(r1.s3_key),
                fastq_2=to_uri(r2.s3_key) if r2 else None,
                files=(r1, r2) if r2 else (r1,),
            )
        )
    problems = []
    if missing_r1:
        problems.append(f"No verified R1 FASTQ for sample(s): {', '.join(missing_r1)}")
    if missing_r2:
        problems.append(
            f"nf-core/{pipeline_id} needs paired reads; no verified R2 from the same "
            f"sequencing run for sample(s): {', '.join(missing_r2)}"
        )
    if problems:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=". ".join(problems)
        )
    return entries
