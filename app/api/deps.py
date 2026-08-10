"""FastAPI dependencies: DB session, auth, RBAC, workspace header."""

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

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/login",
    auto_error=True,
)


async def get_workspace(
    x_labchain_workspace: Annotated[str | None, Header(alias="X-LabChain-Workspace")] = None,
) -> str:
    workspace = (x_labchain_workspace or settings.default_workspace).strip()
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-LabChain-Workspace header must not be empty",
        )
    return workspace


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


class RequireRole:
    """Dependency enforcing that the authenticated user has one of the allowed roles."""

    def __init__(self, *roles: Role | str) -> None:
        self.allowed_roles: set[Role] = {
            role if isinstance(role, Role) else Role(role) for role in roles
        }

    async def __call__(self, current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{current_user.role.value}' is not permitted. "
                    f"Required: {[role.value for role in self.allowed_roles]}"
                ),
            )
        return current_user


require_lab_or_lead = RequireRole(Role.lab_technician, Role.bioinformatics_lead)
require_bioinformatics_lead = RequireRole(Role.bioinformatics_lead)

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Workspace = Annotated[str, Depends(get_workspace)]
LabOrLead = Annotated[User, Depends(require_lab_or_lead)]
BioinformaticsLead = Annotated[User, Depends(require_bioinformatics_lead)]
