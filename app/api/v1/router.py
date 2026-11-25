"""API v1 master router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    fastq,
    pipelines,
    results,
    runs,
    samples,
    sequencing_runs,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(samples.router)
api_router.include_router(sequencing_runs.router)
api_router.include_router(fastq.router)
api_router.include_router(pipelines.router)
api_router.include_router(runs.router)
api_router.include_router(results.router)
