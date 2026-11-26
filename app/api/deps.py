"""FastAPI dependencies: DB session, auth, workspace membership, RBAC."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.api_token import ApiToken
from app.models.user import Role, User
from app.models.workspace import Workspace as WorkspaceModel
from app.models.workspace import WorkspaceMembership
from app.services import api_tokens

WORKSPACE_HEADER = "X-Titerlane-Workspace"

# "function" scope: the session commits when the endpoint returns, before the response is sent.
# With FastAPI's default ("request") scope a yield dependency exits after the response, so a
# client could act on a 2xx before its write is visible, and a commit failure (with its audit
# record) would be lost after the client was told the write succeeded.
DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]

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


@dataclass(frozen=True)
class AuthContext:
    """The authenticated user, and the personal access token used, if any."""

    user: User
    api_token: ApiToken | None = None


async def get_auth_context(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbSession,
) -> AuthContext:
    """Accept a login JWT or a personal access token (``lcb_pat_…``) as bearer credential."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    api_token: ApiToken | None = None
    if api_tokens.is_api_token(token):
        api_token = await api_tokens.authenticate(db, token)
        if api_token is None:
            raise credentials_exception
        user_id = api_token.user_id
    else:
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
    return AuthContext(user=user, api_token=api_token)


async def get_current_user(
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> User:
    return context.user


async def require_interactive_session(
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> User:
    """
    Refuse personal access tokens: a leaked token must not be able to mint new tokens and
    outlive its own revocation. The user signs in (login JWT) to create one.
    """
    if context.api_token is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires signing in; personal access tokens cannot perform it",
        )
    return context.user


async def get_membership(
    x_titerlane_workspace: Annotated[str | None, Header(alias=WORKSPACE_HEADER)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: DbSession,
) -> WorkspaceMembership:
    """
    Resolve the workspace header to a membership of the current user.

    A workspace that does not exist, is inactive, or that the user is not a member of all
    yield the same 404, so the API never reveals which workspaces exist.
    """
    slug = parse_workspace_header(x_titerlane_workspace)
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

CurrentUser = Annotated[User, Depends(get_current_user)]
InteractiveUser = Annotated[User, Depends(require_interactive_session)]
Membership = Annotated[WorkspaceMembership, Depends(get_membership)]
Workspace = Annotated[str, Depends(get_workspace)]
LabOrLead = Annotated[User, Depends(require_lab_or_lead)]
BioinformaticsLead = Annotated[User, Depends(require_bioinformatics_lead)]
