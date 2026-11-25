"""Sample lookup across endpoints and server-managed sample status transitions."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import SequencingRun
from app.models.sample import Sample, SampleStatus
from app.models.user import User
from app.services.audit_service import audit_service

# Status only moves forward. Re-sequencing a completed sample is a new FASTQ registration,
# which does not reopen it; re-running a pipeline moves it back to ``processing``.
_ORDER = {
    SampleStatus.registered: 0,
    SampleStatus.fastq_received: 1,
    SampleStatus.processing: 2,
    SampleStatus.completed: 3,
}


async def get_workspace_samples(
    db: AsyncSession, workspace: str, sample_ids: Iterable[uuid.UUID]
) -> list[Sample]:
    """Load samples by id, all of which must belong to ``workspace`` (else 422)."""
    wanted = list(dict.fromkeys(sample_ids))
    if not wanted:
        return []
    result = await db.execute(
        select(Sample).where(
            Sample.workspace == workspace, Sample.id.in_(wanted), Sample.is_active()
        )
    )
    found = {sample.id: sample for sample in result.scalars().all()}
    missing = [str(sample_id) for sample_id in wanted if sample_id not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown sample id(s) in workspace '{workspace}': {', '.join(missing)}",
        )
    return [found[sample_id] for sample_id in wanted]


async def get_workspace_sequencing_run(
    db: AsyncSession, workspace: str, run_id: uuid.UUID
) -> SequencingRun:
    result = await db.execute(
        select(SequencingRun).where(
            SequencingRun.id == run_id, SequencingRun.workspace == workspace
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown sequencing run id in workspace '{workspace}': {run_id}",
        )
    return run


async def set_status(
    db: AsyncSession,
    samples: Iterable[Sample],
    new_status: SampleStatus,
    *,
    actor: User | None,
    reason: str,
    allow_backward_to_processing: bool = False,
) -> None:
    """Move samples to ``new_status`` (forward only, see ``_ORDER``) and audit each change."""
    for sample in samples:
        current = sample.status
        moves_forward = _ORDER[new_status] > _ORDER[current]
        rerun = (
            allow_backward_to_processing
            and new_status == SampleStatus.processing
            and current == SampleStatus.completed
        )
        if not (moves_forward or rerun):
            continue
        sample.status = new_status
        await db.flush()
        await audit_service.record(
            db,
            actor=actor,
            action="status_change",
            entity_type="sample",
            entity_id=sample.id,
            workspace=sample.workspace,
            before_state={"status": current.value},
            after_state={"status": new_status.value},
            reason=reason,
        )


async def soft_delete(
    db: AsyncSession,
    sample: Sample,
    *,
    actor: User,
    action: str,
    before_state: dict[str, Any],
) -> None:
    """
    Delete a sample without removing its row (21 CFR Part 11): it disappears from the API,
    while its FASTQ files, run outputs and audit trail keep pointing to it.
    """
    sample.deleted_at = datetime.now(UTC)
    await db.flush()
    await audit_service.record(
        db,
        actor=actor,
        action=action,
        entity_type="sample",
        entity_id=sample.id,
        workspace=sample.workspace,
        before_state=before_state,
        after_state={"deletedAt": sample.deleted_at.isoformat()},
    )
