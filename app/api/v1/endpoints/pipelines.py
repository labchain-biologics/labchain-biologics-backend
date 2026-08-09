"""nf-core pipeline catalog endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import LabOrLead
from app.schemas.pipeline import PipelineCatalogItem
from app.services.pipelines_catalog import get_pipeline, list_pipelines

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.get("", response_model=list[PipelineCatalogItem])
async def get_pipelines(_: LabOrLead) -> list[PipelineCatalogItem]:
    return list_pipelines()


@router.get("/{pipeline_id}", response_model=PipelineCatalogItem)
async def get_pipeline_by_id(pipeline_id: str, _: LabOrLead) -> PipelineCatalogItem:
    pipeline = get_pipeline(pipeline_id)
    if pipeline is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline '{pipeline_id}' not found in nf-core catalog",
        )
    return pipeline
