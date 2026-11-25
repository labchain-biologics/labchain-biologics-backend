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
    assert pipeline.version == "3.4.4"
    assert pipeline.version in pipeline.versions
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


def test_every_pipeline_default_version_is_launchable() -> None:
    for item in list_pipelines():
        assert item.version in item.versions, item.id


def test_catalog_covers_web_client_pipelines() -> None:
    ids = {item.id for item in list_pipelines()}
    assert {"sarek", "rnaseq", "scrnaseq", "ampliseq", "atacseq", "mag", "methylseq"} <= ids
