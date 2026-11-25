"""FastAPI dependencies: DB session, auth, workspace membership, RBAC."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import Role, User
from app.models.workspace import Workspace as WorkspaceModel
from app.models.workspace import WorkspaceMembership

WORKSPACE_HEADER = "X-LabChain-Workspace"

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/login",
    auto_error=True,
)


def parse_workspace_header(value: str | None) -> str:
    """Validate the raw workspace header and return the workspace slug."""
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{WORKSPACE_HEADER} header is required",
        )
    slug = value.strip()
    if slug == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{WORKSPACE_HEADER} header must not be empty",
        )
    return slug


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        if subject is None:
            raise credentials_exception
        user_id = uuid.UUID(str(subject))
    except (InvalidTokenError, ValueError, TypeError) as exc:
        raise credentials_exception from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


async def get_membership(
    x_labchain_workspace: Annotated[str | None, Header(alias=WORKSPACE_HEADER)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceMembership:
    """
    Resolve the workspace header to a membership of the current user.

    A workspace that does not exist, is inactive, or that the user is not a member of all
    yield the same 404, so the API never reveals which workspaces exist.
    """
    slug = parse_workspace_header(x_labchain_workspace)
    result = await db.execute(
        select(WorkspaceMembership)
        .join(WorkspaceModel, WorkspaceMembership.workspace_id == WorkspaceModel.id)
        .where(
            WorkspaceModel.slug == slug,
            WorkspaceModel.is_active.is_(True),
            WorkspaceMembership.user_id == current_user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace '{slug}' not found",
        )
    return membership


async def get_workspace(
    membership: Annotated[WorkspaceMembership, Depends(get_membership)],
) -> str:
    """Slug of the workspace the current user is a verified member of."""
    return membership.workspace.slug


class RequireRole:
    """Require the current user to hold one of ``roles`` in the requested workspace."""

    def __init__(self, *roles: Role | str) -> None:
        self.allowed_roles: set[Role] = {
            role if isinstance(role, Role) else Role(role) for role in roles
        }

    async def __call__(
        self,
        membership: Annotated[WorkspaceMembership, Depends(get_membership)],
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if membership.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{membership.role.value}' is not permitted in this workspace. "
                    f"Required: {sorted(role.value for role in self.allowed_roles)}"
                ),
            )
        return current_user


require_lab_or_lead = RequireRole(Role.lab_technician, Role.bioinformatics_lead)
require_bioinformatics_lead = RequireRole(Role.bioinformatics_lead)

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Membership = Annotated[WorkspaceMembership, Depends(get_membership)]
Workspace = Annotated[str, Depends(get_workspace)]
LabOrLead = Annotated[User, Depends(require_lab_or_lead)]
BioinformaticsLead = Annotated[User, Depends(require_bioinformatics_lead)]
