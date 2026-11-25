"""Sequencing runs (flowcells) that FASTQ files are attached to."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DbSession, LabOrLead, Workspace
from app.models.pipeline import SequencingRun
from app.schemas.pipeline import SequencingRunCreate, SequencingRunRead
from app.services.audit_service import audit_service

router = APIRouter(prefix="/sequencing-runs", tags=["sequencing-runs"])


@router.get("", response_model=list[SequencingRunRead])
async def list_sequencing_runs(
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[SequencingRun]:
    result = await db.execute(
        select(SequencingRun)
        .where(SequencingRun.workspace == workspace)
        .order_by(SequencingRun.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


@router.post("", response_model=SequencingRunRead, status_code=status.HTTP_201_CREATED)
async def create_sequencing_run(
    payload: SequencingRunCreate,
    db: DbSession,
    workspace: Workspace,
    current_user: LabOrLead,
) -> SequencingRun:
    run = SequencingRun(workspace=workspace, created_by=current_user.id, **payload.model_dump())
    db.add(run)
    await db.flush()
    await audit_service.record(
        db,
        actor=current_user,
        action="create",
        entity_type="sequencing_run",
        entity_id=run.id,
        workspace=workspace,
        after_state=payload.model_dump(mode="json", by_alias=True),
    )
    return run


@router.get("/{run_id}", response_model=SequencingRunRead)
async def get_sequencing_run(
    run_id: uuid.UUID,
    db: DbSession,
    workspace: Workspace,
    _: LabOrLead,
) -> SequencingRun:
    result = await db.execute(
        select(SequencingRun).where(
            SequencingRun.id == run_id, SequencingRun.workspace == workspace
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sequencing run {run_id} not found",
        )
    return run
