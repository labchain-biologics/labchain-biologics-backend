"""
Operator actions run from the server host (``titerlane-admin``), outside the HTTP API.

They exist for what the API cannot do on a production instance: create the first user (self
registration is disabled) and grant workspace access without an existing lead. Every action is
written to the audit trail with no user actor and a reason naming the command:
``operator create-user`` or ``operator grant`` (the reason the former
``scripts/grant_membership.py`` recorded, kept so audit queries stay valid).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import Role, User
from app.models.workspace import Workspace, WorkspaceMembership
from app.schemas.auth import LoginRequest
from app.schemas.workspace import WorkspaceCreate
from app.services.audit_service import audit_service
from app.services.workspace_service import membership_audit_state

CREATE_USER_REASON = "operator create-user"
GRANT_REASON = "operator grant"
FULL_NAME_MAX_LENGTH = 255


class OperatorError(Exception):
    """An operator action was refused; the message is safe to print."""


@dataclass(frozen=True, slots=True)
class MembershipGrant:
    email: str
    workspace: str
    role: Role
    created_workspace: bool
    changed: bool


async def create_user(db: AsyncSession, *, email: str, password: str, full_name: str) -> User:
    """Create an active password user. Same rules as the API: valid email, 8-128 chars."""
    try:
        credentials = LoginRequest(email=email, password=password)
    except ValidationError as exc:
        fields = ", ".join(str(error["loc"][-1]) for error in exc.errors())
        raise OperatorError(f"Invalid {fields}") from None
    full_name = full_name.strip()
    if len(full_name) > FULL_NAME_MAX_LENGTH:
        raise OperatorError(f"Invalid full name: at most {FULL_NAME_MAX_LENGTH} characters")
    normalized = credentials.email.lower()
    if await db.scalar(select(User).where(User.email == normalized)) is not None:
        raise OperatorError(f"A user with email {normalized} already exists")
    user = User(
        email=normalized,
        full_name=full_name or normalized.split("@")[0],
        hashed_password=hash_password(credentials.password),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await audit_service.record(
        db,
        action="create",
        entity_type="user",
        entity_id=user.id,
        workspace=None,
        after_state={"email": user.email, "fullName": user.full_name},
        reason=CREATE_USER_REASON,
    )
    return user


async def grant_membership(
    db: AsyncSession,
    *,
    email: str,
    workspace_slug: str,
    role: Role,
    create_workspace: bool = False,
    workspace_name: str | None = None,
) -> MembershipGrant:
    """Give a user a role in a workspace, optionally creating the workspace."""
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        raise OperatorError(f"No user with email {email.lower()}")
    if not user.is_active:
        raise OperatorError(f"User {user.email} is deactivated: access would have no effect")
    workspace = await db.scalar(select(Workspace).where(Workspace.slug == workspace_slug))
    created = False
    if workspace is not None and not workspace.is_active:
        raise OperatorError(f"Workspace '{workspace_slug}' is deactivated")
    if workspace is None:
        if not create_workspace:
            raise OperatorError(f"No workspace '{workspace_slug}' (pass --create to create it)")
        # Same rules as POST /workspaces: the slug prefixes storage keys and is the tenant header.
        try:
            spec = WorkspaceCreate(slug=workspace_slug, name=workspace_name or workspace_slug)
        except ValidationError as exc:
            fields = ", ".join(str(error["loc"][-1]) for error in exc.errors())
            raise OperatorError(
                f"Invalid workspace {fields}: the slug takes lowercase letters, digits and "
                "dashes (at most 64), the name at most 255 characters"
            ) from None
        workspace = Workspace(slug=spec.slug, name=spec.name, is_active=True)
        db.add(workspace)
        await db.flush()
        created = True
        await audit_service.record(
            db,
            action="create",
            entity_type="workspace",
            entity_id=workspace.id,
            workspace=workspace_slug,
            after_state={"slug": workspace_slug, "name": workspace.name},
            reason=GRANT_REASON,
        )
    else:
        await _lock_workspace(db, workspace.id)
    membership = await db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace.id,
            WorkspaceMembership.user_id == user.id,
        )
    )
    # Same audit shape as role changes made through the API (workspace_service).
    before = membership_audit_state(membership, user.email) if membership else None
    if membership is not None and membership.role == role:
        return MembershipGrant(user.email, workspace_slug, role, created, changed=False)
    if (
        membership is not None
        and membership.role == Role.bioinformatics_lead
        and await _lead_count(db, workspace.id) <= 1
    ):
        raise OperatorError(
            f"{user.email} is the only bioinformatics_lead of '{workspace_slug}': "
            "grant the role to someone else first"
        )
    if membership is None:
        membership = WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role=role)
        db.add(membership)
    else:
        membership.role = role
    await db.flush()
    await audit_service.record(
        db,
        action="add_member" if before is None else "change_role",
        entity_type="workspace_membership",
        entity_id=membership.id,
        workspace=workspace_slug,
        before_state=before,
        after_state=membership_audit_state(membership, user.email),
        reason=GRANT_REASON,
    )
    return MembershipGrant(user.email, workspace_slug, role, created, changed=True)


async def _lock_workspace(db: AsyncSession, workspace_id: uuid.UUID) -> None:
    """Serialize role changes with the API (same row lock as workspace_service)."""
    await db.execute(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())


async def _lead_count(db: AsyncSession, workspace_id: uuid.UUID) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(WorkspaceMembership)
        .where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.role == Role.bioinformatics_lead,
        )
    )
    return int(count or 0)
