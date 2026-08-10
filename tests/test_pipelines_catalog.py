"""Unit tests for the in-memory nf-core pipeline catalog."""

from __future__ import annotations

from app.services.pipelines_catalog import get_pipeline, list_pipelines


def test_list_pipelines_returns_known_catalog() -> None:
    pipelines = list_pipelines()
    ids = {item.id for item in pipelines}
    assert {"rnaseq", "sarek", "atacseq", "chipseq", "viralrecon", "ampliseq"} <= ids
    assert all(item.nf_core for item in pipelines)


def test_get_pipeline_returns_item() -> None:
    pipeline = get_pipeline("sarek")
    assert pipeline is not None
    assert pipeline.name == "nf-core/sarek"
    assert pipeline.version == "3.4.0"
    assert "variant-calling" in pipeline.categories


def test_get_pipeline_unknown_returns_none() -> None:
    assert get_pipeline("does-not-exist") is None


def test_pipeline_catalog_serializes_camel_case() -> None:
    pipeline = get_pipeline("rnaseq")
    assert pipeline is not None
    dumped = pipeline.model_dump(by_alias=True)
    assert dumped["nfCore"] is True
    assert "defaultParams" in dumped
    assert dumped["defaultParams"]["aligner"] == "star_salmon"
