"""Workspace creation and membership management."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Role, User
from app.models.workspace import Workspace, WorkspaceMembership
from app.services.audit_service import audit_service


def _membership_state(membership: WorkspaceMembership, email: str) -> dict[str, str]:
    return {"userId": str(membership.user_id), "email": email, "role": membership.role.value}


class WorkspaceService:
    async def create_workspace(
        self, db: AsyncSession, *, slug: str, name: str, creator: User
    ) -> tuple[Workspace, WorkspaceMembership]:
        existing = await db.execute(select(Workspace.id).where(Workspace.slug == slug))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Workspace slug '{slug}' is already taken",
            )
        workspace = Workspace(slug=slug, name=name, created_by=creator.id, is_active=True)
        db.add(workspace)
        await db.flush()

        membership = WorkspaceMembership(
            workspace_id=workspace.id, user_id=creator.id, role=Role.bioinformatics_lead
        )
        db.add(membership)
        await db.flush()

        await audit_service.record(
            db,
            actor=creator,
            action="create",
            entity_type="workspace",
            entity_id=workspace.id,
            workspace=workspace.slug,
            after_state={"slug": workspace.slug, "name": workspace.name},
        )
        await audit_service.record(
            db,
            actor=creator,
            action="add_member",
            entity_type="workspace_membership",
            entity_id=membership.id,
            workspace=workspace.slug,
            after_state=_membership_state(membership, creator.email),
        )
        return workspace, membership

    async def list_members(
        self, db: AsyncSession, *, workspace_id: uuid.UUID
    ) -> list[tuple[WorkspaceMembership, User]]:
        result = await db.execute(
            select(WorkspaceMembership, User)
            .join(User, WorkspaceMembership.user_id == User.id)
            .where(WorkspaceMembership.workspace_id == workspace_id)
            .order_by(User.email)
        )
        return [(membership, user) for membership, user in result.all()]

    async def add_member(
        self,
        db: AsyncSession,
        *,
        workspace: Workspace,
        email: str,
        role: Role,
        actor: User,
    ) -> tuple[WorkspaceMembership, User]:
        user_result = await db.execute(select(User).where(User.email == email.lower()))
        user = user_result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No user with email '{email}'. The user must have an account first.",
            )
        existing = await self._find(db, workspace_id=workspace.id, user_id=user.id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{user.email} is already a member of this workspace",
            )
        membership = WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role=role)
        db.add(membership)
        await db.flush()
        await audit_service.record(
            db,
            actor=actor,
            action="add_member",
            entity_type="workspace_membership",
            entity_id=membership.id,
            workspace=workspace.slug,
            after_state=_membership_state(membership, user.email),
        )
        return membership, user

    async def change_role(
        self,
        db: AsyncSession,
        *,
        workspace: Workspace,
        user_id: uuid.UUID,
        role: Role,
        actor: User,
    ) -> tuple[WorkspaceMembership, User]:
        await self._lock_workspace(db, workspace.id)
        membership, user = await self._get_member(db, workspace_id=workspace.id, user_id=user_id)
        if membership.role == role:
            return membership, user
        if membership.role == Role.bioinformatics_lead:
            await self._ensure_not_last_lead(db, workspace_id=workspace.id)
        before = _membership_state(membership, user.email)
        membership.role = role
        await db.flush()
        await audit_service.record(
            db,
            actor=actor,
            action="change_role",
            entity_type="workspace_membership",
            entity_id=membership.id,
            workspace=workspace.slug,
            before_state=before,
            after_state=_membership_state(membership, user.email),
        )
        return membership, user

    async def remove_member(
        self,
        db: AsyncSession,
        *,
        workspace: Workspace,
        user_id: uuid.UUID,
        actor: User,
    ) -> None:
        await self._lock_workspace(db, workspace.id)
        membership, user = await self._get_member(db, workspace_id=workspace.id, user_id=user_id)
        if membership.role == Role.bioinformatics_lead:
            await self._ensure_not_last_lead(db, workspace_id=workspace.id)
        before = _membership_state(membership, user.email)
        membership_id = membership.id
        await db.delete(membership)
        await db.flush()
        await audit_service.record(
            db,
            actor=actor,
            action="remove_member",
            entity_type="workspace_membership",
            entity_id=membership_id,
            workspace=workspace.slug,
            before_state=before,
        )

    async def _lock_workspace(self, db: AsyncSession, workspace_id: uuid.UUID) -> None:
        """
        Serialize role changes and removals in a workspace, so two concurrent requests
        cannot both pass the last-lead check. Held until the transaction ends.
        """
        await db.execute(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())

    async def _find(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceMembership | None:
        result = await db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_member(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[WorkspaceMembership, User]:
        result = await db.execute(
            select(WorkspaceMembership, User)
            .join(User, WorkspaceMembership.user_id == User.id)
            .where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
            # Re-read after taking the workspace lock: the role may have just changed.
            .execution_options(populate_existing=True)
        )
        row = result.one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} is not a member of this workspace",
            )
        membership, user = row
        return membership, user

    async def _ensure_not_last_lead(self, db: AsyncSession, *, workspace_id: uuid.UUID) -> None:
        result = await db.execute(
            select(func.count())
            .select_from(WorkspaceMembership)
            .where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.role == Role.bioinformatics_lead,
            )
        )
        if int(result.scalar_one()) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A workspace must keep at least one bioinformatics_lead",
            )


workspace_service = WorkspaceService()
