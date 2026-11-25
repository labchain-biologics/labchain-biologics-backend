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


class UnsupportedPipelineError(ValueError):
    """The pipeline needs metadata the LIMS does not hold, so no samplesheet can be built."""


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
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for entry in entries:
        writer.writerow(build(entry))
    return buffer.getvalue()


def _latest(files: list[FastqFile], read_pair: str) -> FastqFile | None:
    matching = [f for f in files if (f.read_pair or "").upper() == read_pair]
    return max(matching, key=lambda f: f.created_at) if matching else None


async def collect_entries(
    db: AsyncSession,
    samples: Sequence[Sample],
    to_uri: Callable[[str], str],
) -> list[SamplesheetEntry]:
    """
    Pick, for each sample, its most recent verified R1 (required) and R2 (optional, same
    sequencing run as R1 when possible). Raises 422 naming every sample without reads.
    """
    if not samples:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Select at least one sample to build the samplesheet",
        )
    result = await db.execute(
        select(FastqFile).where(
            FastqFile.sample_id.in_([s.id for s in samples]),
            FastqFile.verification_status == FastqVerificationStatus.verified,
        )
    )
    by_sample: dict[object, list[FastqFile]] = {}
    for fastq in result.scalars().all():
        by_sample.setdefault(fastq.sample_id, []).append(fastq)

    entries: list[SamplesheetEntry] = []
    missing: list[str] = []
    for sample in samples:
        files = by_sample.get(sample.id, [])
        r1 = _latest(files, "R1")
        if r1 is None:
            missing.append(sample.sample_code)
            continue
        same_run = [f for f in files if f.sequencing_run_id == r1.sequencing_run_id]
        r2 = _latest(same_run, "R2") or _latest(files, "R2")
        entries.append(
            SamplesheetEntry(
                sample=sample,
                fastq_1=to_uri(r1.s3_key),
                fastq_2=to_uri(r2.s3_key) if r2 else None,
            )
        )
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"No verified R1 FASTQ for sample(s): {', '.join(missing)}",
        )
    return entries
