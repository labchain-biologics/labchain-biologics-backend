"""In-memory nf-core pipeline catalog."""

from __future__ import annotations

from app.schemas.pipeline import PipelineCatalogItem

NF_CORE_CATALOG: dict[str, PipelineCatalogItem] = {
    "rnaseq": PipelineCatalogItem(
        id="rnaseq",
        name="nf-core/rnaseq",
        description="RNA sequencing analysis pipeline using STAR, RSEM, HISAT2 or Salmon.",
        version="3.14.0",
        nf_core=True,
        categories=["transcriptomics", "rna"],
        default_params={"aligner": "star_salmon", "fasta": None, "gtf": None},
    ),
    "sarek": PipelineCatalogItem(
        id="sarek",
        name="nf-core/sarek",
        description="Analysis pipeline to detect germline or somatic variants from WGS/WES.",
        version="3.4.0",
        nf_core=True,
        categories=["genomics", "variant-calling"],
        default_params={"tools": "haplotypecaller", "genome": "GATK.GRCh38"},
    ),
    "atacseq": PipelineCatalogItem(
        id="atacseq",
        name="nf-core/atacseq",
        description="ATAC-seq peak-calling and QC pipeline using BWA and MACS2.",
        version="2.1.2",
        nf_core=True,
        categories=["epigenomics", "atac"],
        default_params={"genome": "GRCh38", "narrow_peak": True},
    ),
    "chipseq": PipelineCatalogItem(
        id="chipseq",
        name="nf-core/chipseq",
        description="ChIP-seq peak-calling and differential analysis pipeline.",
        version="2.0.0",
        nf_core=True,
        categories=["epigenomics", "chip"],
        default_params={"genome": "GRCh38"},
    ),
    "viralrecon": PipelineCatalogItem(
        id="viralrecon",
        name="nf-core/viralrecon",
        description="Assembly and intrahost/low-frequency variant calling for viral samples.",
        version="2.6.0",
        nf_core=True,
        categories=["genomics", "virology"],
        default_params={"platform": "illumina", "protocol": "metagenomic"},
    ),
    "ampliseq": PipelineCatalogItem(
        id="ampliseq",
        name="nf-core/ampliseq",
        description="16S rRNA amplicon sequencing analysis workflow.",
        version="2.9.0",
        nf_core=True,
        categories=["metagenomics", "amplicon"],
        default_params={"FW_primer": None, "RV_primer": None},
    ),
}


def list_pipelines() -> list[PipelineCatalogItem]:
    return list(NF_CORE_CATALOG.values())


def get_pipeline(pipeline_id: str) -> PipelineCatalogItem | None:
    return NF_CORE_CATALOG.get(pipeline_id)
