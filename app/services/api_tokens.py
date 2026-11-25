"""Personal access tokens: issue, authenticate, list and revoke."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.api_token import ApiToken
from app.models.user import User
from app.services.audit_service import audit_service

# Distinguishes a personal access token from a login JWT in the Authorization header, and
# lets secret scanners recognise leaked tokens.
TOKEN_PREFIX = "lcb_pat_"
# Characters kept in clear (``lcb_pat_`` + 8 random characters) so users can tell tokens apart.
DISPLAY_PREFIX_LENGTH = len(TOKEN_PREFIX) + 8
# ``last_used_at`` is refreshed at most once per interval, not on every request.
LAST_USED_RESOLUTION = timedelta(minutes=1)


def is_api_token(credential: str) -> bool:
    return credential.startswith(TOKEN_PREFIX)


def hash_token(secret: str) -> str:
    """SHA-256 hex digest. The secret carries 256 random bits, so no salt or slow hash is needed."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_secret() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def _audit_state(token: ApiToken) -> dict[str, str | None]:
    """Audit payload: never the secret nor its digest."""
    return {
        "name": token.name,
        "tokenPrefix": token.token_prefix,
        "expiresAt": token.expires_at.isoformat(),
        "revokedAt": token.revoked_at.isoformat() if token.revoked_at else None,
    }


async def create(
    db: AsyncSession, user: User, *, name: str, lifetime_days: int | None
) -> tuple[ApiToken, str]:
    """Issue a token for ``user``. Returns the stored row and the secret, shown only once."""
    days = lifetime_days if lifetime_days is not None else settings.api_token_default_lifetime_days
    if days > settings.api_token_max_lifetime_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"expiresInDays must be at most {settings.api_token_max_lifetime_days} "
                "on this server"
            ),
        )
    secret = generate_secret()
    now = datetime.now(UTC)
    token = ApiToken(
        id=uuid.uuid4(),
        user_id=user.id,
        name=name,
        token_hash=hash_token(secret),
        token_prefix=secret[:DISPLAY_PREFIX_LENGTH],
        # Set here rather than by the server default, so the row is complete after flush.
        created_at=now,
        expires_at=now + timedelta(days=days),
    )
    db.add(token)
    await db.flush()
    await audit_service.record(
        db,
        actor=user,
        action="create",
        entity_type="api_token",
        entity_id=token.id,
        workspace=None,
        after_state=_audit_state(token),
    )
    return token, secret


async def authenticate(db: AsyncSession, secret: str) -> ApiToken | None:
    """The active token matching ``secret``, or ``None`` if unknown, revoked or expired."""
    result = await db.execute(select(ApiToken).where(ApiToken.token_hash == hash_token(secret)))
    token = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if token is None or token.revoked_at is not None or token.expires_at <= now:
        return None
    # Usage metadata, not a change to the token itself: not written to the audit trail.
    if token.last_used_at is None or now - token.last_used_at >= LAST_USED_RESOLUTION:
        token.last_used_at = now
        await db.flush()
    return token


async def list_for_user(db: AsyncSession, user: User) -> list[ApiToken]:
    result = await db.execute(
        select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc())
    )
    return list(result.scalars().all())


async def get_for_user(db: AsyncSession, user: User, token_id: uuid.UUID) -> ApiToken:
    """A token owned by ``user``. Another user's token yields the same 404 as a missing one."""
    result = await db.execute(
        select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user.id)
    )
    token = result.scalar_one_or_none()
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API token {token_id} not found",
        )
    return token


async def revoke(db: AsyncSession, user: User, token: ApiToken) -> ApiToken:
    if token.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"API token {token.id} is already revoked",
        )
    before = _audit_state(token)
    token.revoked_at = datetime.now(UTC)
    await db.flush()
    await audit_service.record(
        db,
        actor=user,
        action="revoke",
        entity_type="api_token",
        entity_id=token.id,
        workspace=None,
        before_state=before,
        after_state=_audit_state(token),
    )
    return token
