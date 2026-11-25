"""Unit tests for nf-core samplesheet rendering."""

from __future__ import annotations

import csv
import io

import pytest

from app.models.sample import OmicsModality, Sample, SampleType
from app.services.samplesheet import (
    SamplesheetEntry,
    UnsupportedPipelineError,
    build_samplesheet,
    supports,
)


def _entry(
    code: str, *, sample_type: SampleType | None = None, r2: bool = True
) -> SamplesheetEntry:
    sample = Sample(
        sample_code=code,
        modality=OmicsModality.genomics,
        sample_type=sample_type,
        patient_id="PT 9",
        paired_group="grp-1",
    )
    return SamplesheetEntry(
        sample=sample,
        fastq_1=f"s3://b/{code}_R1.fastq.gz",
        fastq_2=f"s3://b/{code}_R2.fastq.gz" if r2 else None,
    )


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_sarek_marks_tumor_status_and_patient() -> None:
    entries = [
        _entry("T-1", sample_type=SampleType.tumor),
        _entry("N-1", sample_type=SampleType.normal),
    ]
    rows = _rows(build_samplesheet("sarek", entries))
    assert [(r["patient"], r["sample"], r["status"]) for r in rows] == [
        ("PT_9", "T-1", "1"),
        ("PT_9", "N-1", "0"),
    ]
    assert rows[0]["fastq_2"] == "s3://b/T-1_R2.fastq.gz"


def test_rnaseq_uses_auto_strandedness_and_allows_single_end() -> None:
    rows = _rows(build_samplesheet("rnaseq", [_entry("RNA 1", r2=False)]))
    assert rows == [
        {
            "sample": "RNA_1",
            "fastq_1": "s3://b/RNA 1_R1.fastq.gz",
            "fastq_2": "",
            "strandedness": "auto",
        }
    ]


def test_ampliseq_ids_start_with_a_letter() -> None:
    rows = _rows(build_samplesheet("ampliseq", [_entry("16S-001")]))
    assert list(rows[0]) == ["sampleID", "forwardReads", "reverseReads"]
    assert rows[0]["sampleID"] == "S_16S_001"


def test_mag_groups_by_paired_group() -> None:
    rows = _rows(build_samplesheet("mag", [_entry("MG1")]))
    assert rows[0]["group"] == "grp-1"
    assert rows[0]["long_reads"] == ""


def test_unsupported_pipeline() -> None:
    assert not supports("chipseq")
    with pytest.raises(UnsupportedPipelineError):
        build_samplesheet("chipseq", [_entry("C1")])


@pytest.mark.parametrize(
    "pipeline",
    ["rnaseq", "sarek", "scrnaseq", "atacseq", "methylseq", "viralrecon", "ampliseq", "mag"],
)
def test_every_supported_pipeline_renders_a_header_and_rows(pipeline: str) -> None:
    text = build_samplesheet(pipeline, [_entry("A1"), _entry("A2")])
    assert len(text.strip().splitlines()) == 3
