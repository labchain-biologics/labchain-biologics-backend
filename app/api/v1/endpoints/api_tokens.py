"""Personal access tokens of the current user."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession, InteractiveUser
from app.models.api_token import ApiToken
from app.schemas.api_token import ApiTokenCreate, ApiTokenCreated, ApiTokenRead
from app.services import api_tokens

router = APIRouter(prefix="/auth/tokens", tags=["auth"])


@router.post("", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
async def create_api_token(
    payload: ApiTokenCreate,
    db: DbSession,
    current_user: InteractiveUser,
) -> ApiTokenCreated:
    """
    Issue a personal access token acting as the current user, with their per-workspace roles.
    Requires a login JWT: a personal access token cannot create another one.
    """
    token, secret = await api_tokens.create(
        db, current_user, name=payload.name, lifetime_days=payload.expires_in_days
    )
    return ApiTokenCreated(
        id=token.id,
        name=token.name,
        token_prefix=token.token_prefix,
        created_at=token.created_at,
        expires_at=token.expires_at,
        last_used_at=token.last_used_at,
        revoked_at=token.revoked_at,
        token=secret,
    )


@router.get("", response_model=list[ApiTokenRead])
async def list_api_tokens(db: DbSession, current_user: CurrentUser) -> list[ApiToken]:
    """The current user's tokens, newest first, including revoked and expired ones."""
    return await api_tokens.list_for_user(db, current_user)


@router.delete("/{token_id}", response_model=ApiTokenRead)
async def revoke_api_token(
    token_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> ApiToken:
    """Revoke a token (soft delete, audited). It stops working immediately."""
    token = await api_tokens.get_for_user(db, current_user, token_id)
    return await api_tokens.revoke(db, current_user, token)
