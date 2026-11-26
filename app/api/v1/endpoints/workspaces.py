"""Workspace creation, listing and membership management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import BioinformaticsLead, CurrentUser, DbSession, LabOrLead, Membership
from app.core.config import settings
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.schemas.workspace import (
    MemberCreate,
    MemberRead,
    MemberUpdate,
    WorkspaceCreate,
    WorkspaceRead,
)
from app.services.workspace_service import workspace_service

router = APIRouter(tags=["workspaces"])


def _member_read(membership: WorkspaceMembership, user: User) -> MemberRead:
    return MemberRead(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        is_active=user.is_active,
        joined_at=membership.created_at,
    )


@router.get("/workspaces", response_model=list[WorkspaceRead])
async def list_my_workspaces(db: DbSession, current_user: CurrentUser) -> list[WorkspaceRead]:
    result = await db.execute(
        select(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == current_user.id)
        .options(selectinload(WorkspaceMembership.workspace))
    )
    items = [
        WorkspaceRead(
            id=m.workspace.id,
            slug=m.workspace.slug,
            name=m.workspace.name,
            role=m.role,
            created_at=m.workspace.created_at,
        )
        for m in result.scalars().all()
        if m.workspace.is_active
    ]
    return sorted(items, key=lambda item: item.name.lower())


@router.post("/workspaces", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate, db: DbSession, current_user: CurrentUser
) -> WorkspaceRead:
    """Create a workspace. The creator becomes its first ``bioinformatics_lead``."""
    if not settings.workspace_creation_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace creation is disabled on this instance",
        )
    workspace, membership = await workspace_service.create_workspace(
        db, slug=payload.slug, name=payload.name, creator=current_user
    )
    return WorkspaceRead(
        id=workspace.id,
        slug=workspace.slug,
        name=workspace.name,
        role=membership.role,
        created_at=workspace.created_at,
    )


@router.get("/members", response_model=list[MemberRead])
async def list_members(db: DbSession, membership: Membership, _: LabOrLead) -> list[MemberRead]:
    """Members of the workspace named by the ``X-Titerlane-Workspace`` header."""
    rows = await workspace_service.list_members(db, workspace_id=membership.workspace_id)
    return [_member_read(m, user) for m, user in rows]


@router.post("/members", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
async def add_member(
    payload: MemberCreate,
    db: DbSession,
    membership: Membership,
    current_user: BioinformaticsLead,
) -> MemberRead:
    new_membership, user = await workspace_service.add_member(
        db,
        workspace=membership.workspace,
        email=str(payload.email),
        role=payload.role,
        actor=current_user,
    )
    return _member_read(new_membership, user)


@router.patch("/members/{user_id}", response_model=MemberRead)
async def change_member_role(
    user_id: uuid.UUID,
    payload: MemberUpdate,
    db: DbSession,
    membership: Membership,
    current_user: BioinformaticsLead,
) -> MemberRead:
    updated, user = await workspace_service.change_role(
        db,
        workspace=membership.workspace,
        user_id=user_id,
        role=payload.role,
        actor=current_user,
    )
    return _member_read(updated, user)


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    user_id: uuid.UUID,
    db: DbSession,
    membership: Membership,
    current_user: BioinformaticsLead,
) -> None:
    await workspace_service.remove_member(
        db, workspace=membership.workspace, user_id=user_id, actor=current_user
    )
