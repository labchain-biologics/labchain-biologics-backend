"""In-memory nf-core pipeline catalog.

``version`` is the default revision; ``versions`` lists every revision a run may be launched
with (the API rejects others). ``assays`` lists the sample assays the pipeline is suggested for.
"""

from __future__ import annotations

from app.models.sample import SampleAssay
from app.schemas.pipeline import PipelineCatalogItem

NF_CORE_CATALOG: dict[str, PipelineCatalogItem] = {
    "rnaseq": PipelineCatalogItem(
        id="rnaseq",
        name="nf-core/rnaseq",
        description="RNA sequencing analysis pipeline using STAR, RSEM, HISAT2 or Salmon.",
        version="3.14.0",
        versions=["3.14.0", "3.13.2", "3.12.0"],
        nf_core=True,
        categories=["transcriptomics", "rna"],
        assays=[SampleAssay.bulk_rna],
        default_params={"aligner": "star_salmon", "genome": "GRCh38"},
    ),
    "sarek": PipelineCatalogItem(
        id="sarek",
        name="nf-core/sarek",
        description="Analysis pipeline to detect germline or somatic variants from WGS/WES.",
        version="3.4.4",
        versions=["3.4.4", "3.4.0", "3.3.2"],
        nf_core=True,
        categories=["genomics", "variant-calling"],
        assays=[SampleAssay.wgs, SampleAssay.exome, SampleAssay.targeted_panel],
        default_params={"tools": "haplotypecaller", "genome": "GATK.GRCh38"},
    ),
    "scrnaseq": PipelineCatalogItem(
        id="scrnaseq",
        name="nf-core/scrnaseq",
        description="Single-cell RNA-seq: alignment, quantification and QC (STARsolo, Alevin).",
        version="2.7.1",
        versions=["2.7.1", "2.6.0", "2.5.1"],
        nf_core=True,
        categories=["transcriptomics", "single-cell"],
        assays=[SampleAssay.single_cell_rna],
        default_params={"aligner": "star", "genome": "GRCh38", "protocol": "10XV3"},
    ),
    "atacseq": PipelineCatalogItem(
        id="atacseq",
        name="nf-core/atacseq",
        description="ATAC-seq peak-calling and QC pipeline using BWA and MACS2.",
        version="2.1.2",
        versions=["2.1.2", "2.1.1", "2.0.0"],
        nf_core=True,
        categories=["epigenomics", "atac"],
        assays=[SampleAssay.atac_seq],
        default_params={"genome": "GRCh38", "narrow_peak": True},
    ),
    "methylseq": PipelineCatalogItem(
        id="methylseq",
        name="nf-core/methylseq",
        description="Bisulfite sequencing methylation analysis (Bismark or bwa-meth).",
        version="2.6.0",
        versions=["2.6.0", "2.5.0", "2.4.0"],
        nf_core=True,
        categories=["epigenomics", "methylation"],
        assays=[SampleAssay.methylation],
        default_params={"aligner": "bismark", "genome": "GRCh38"},
    ),
    "chipseq": PipelineCatalogItem(
        id="chipseq",
        name="nf-core/chipseq",
        description="ChIP-seq peak-calling and differential analysis pipeline.",
        version="2.0.0",
        versions=["2.0.0"],
        nf_core=True,
        categories=["epigenomics", "chip"],
        assays=[],
        default_params={"genome": "GRCh38"},
    ),
    "ampliseq": PipelineCatalogItem(
        id="ampliseq",
        name="nf-core/ampliseq",
        description="16S rRNA amplicon sequencing analysis workflow.",
        version="2.11.0",
        versions=["2.11.0", "2.9.0", "2.8.0"],
        nf_core=True,
        categories=["metagenomics", "amplicon"],
        assays=[SampleAssay.amplicon_16s],
        default_params={"FW_primer": None, "RV_primer": None},
    ),
    "mag": PipelineCatalogItem(
        id="mag",
        name="nf-core/mag",
        description="Metagenome assembly, binning and taxonomic classification.",
        version="3.0.3",
        versions=["3.0.3", "2.5.4", "2.4.0"],
        nf_core=True,
        categories=["metagenomics", "assembly"],
        assays=[SampleAssay.metagenomics],
        default_params={},
    ),
    "viralrecon": PipelineCatalogItem(
        id="viralrecon",
        name="nf-core/viralrecon",
        description="Assembly and intrahost/low-frequency variant calling for viral samples.",
        version="2.6.0",
        versions=["2.6.0"],
        nf_core=True,
        categories=["genomics", "virology"],
        assays=[],
        default_params={"platform": "illumina", "protocol": "metagenomic"},
    ),
}


def list_pipelines() -> list[PipelineCatalogItem]:
    return list(NF_CORE_CATALOG.values())


def get_pipeline(pipeline_id: str) -> PipelineCatalogItem | None:
    return NF_CORE_CATALOG.get(pipeline_id)
