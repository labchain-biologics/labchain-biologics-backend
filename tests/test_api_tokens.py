"""Unit tests for personal access tokens (service and auth dependencies)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.deps import AuthContext, get_auth_context, require_interactive_session
from app.core.config import settings
from app.core.security import create_access_token
from app.models.api_token import ApiToken
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.api_token import ApiTokenCreate
from app.services import api_tokens


def _token(user: User, **overrides: Any) -> ApiToken:
    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": user.id,
        "name": "ci",
        "token_hash": "0" * 64,
        "token_prefix": "lcb_pat_abcdefgh",
        "created_at": now,
        "expires_at": now + timedelta(days=30),
        "last_used_at": None,
        "revoked_at": None,
    }
    values.update(overrides)
    return ApiToken(**values)


def _db_returning(*rows: object) -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    results = []
    for row in rows:
        result = MagicMock()
        result.scalar_one_or_none.return_value = row
        results.append(result)
    db.execute = AsyncMock(side_effect=results)
    return db


def _audit_entries(db: AsyncMock) -> list[AuditLog]:
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], AuditLog)]


def test_generated_secret_is_prefixed_unique_and_hashed() -> None:
    first, second = api_tokens.generate_secret(), api_tokens.generate_secret()
    assert first.startswith("lcb_pat_") and api_tokens.is_api_token(first)
    assert first != second
    assert len(api_tokens.hash_token(first)) == 64
    assert api_tokens.hash_token(first) != api_tokens.hash_token(second)


def test_jwt_is_not_mistaken_for_api_token() -> None:
    assert not api_tokens.is_api_token(create_access_token("someone"))


@pytest.mark.asyncio
async def test_create_stores_only_digest_and_audits_without_secret(
    sample_user: User, mock_db: AsyncMock
) -> None:
    token, secret = await api_tokens.create(mock_db, sample_user, name="ci", lifetime_days=7)

    assert token.token_hash == api_tokens.hash_token(secret)
    assert token.token_prefix == secret[: api_tokens.DISPLAY_PREFIX_LENGTH]
    assert timedelta(days=6) < token.expires_at - token.created_at <= timedelta(days=7)
    [entry] = _audit_entries(mock_db)
    assert (entry.action, entry.entity_type, entry.workspace) == ("create", "api_token", None)
    serialized = repr(entry.after_state)
    assert secret not in serialized and token.token_hash not in serialized


@pytest.mark.asyncio
async def test_create_uses_default_lifetime(
    sample_user: User, mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "api_token_default_lifetime_days", 10)
    token, _ = await api_tokens.create(mock_db, sample_user, name="ci", lifetime_days=None)
    assert token.expires_at - token.created_at == timedelta(days=10)


@pytest.mark.asyncio
async def test_create_rejects_lifetime_over_server_maximum(
    sample_user: User, mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "api_token_max_lifetime_days", 30)
    with pytest.raises(HTTPException) as exc_info:
        await api_tokens.create(mock_db, sample_user, name="ci", lifetime_days=31)
    assert exc_info.value.status_code == 422
    mock_db.add.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [{"name": "   "}, {"name": ""}, {"name": "x" * 101}, {"name": "ci", "expiresInDays": 0}],
)
def test_create_payload_validation(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ApiTokenCreate.model_validate(payload)


@pytest.mark.asyncio
async def test_authenticate_accepts_active_token_and_records_use(sample_user: User) -> None:
    token = _token(sample_user)
    db = _db_returning(token)
    assert await api_tokens.authenticate(db, "lcb_pat_secret") is token
    assert token.last_used_at is not None


@pytest.mark.asyncio
async def test_authenticate_throttles_last_used_updates(sample_user: User) -> None:
    recent = datetime.now(UTC) - timedelta(seconds=5)
    token = _token(sample_user, last_used_at=recent)
    db = _db_returning(token)
    await api_tokens.authenticate(db, "lcb_pat_secret")
    assert token.last_used_at == recent
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"revoked_at": datetime.now(UTC)},
        {"expires_at": datetime.now(UTC) - timedelta(seconds=1)},
    ],
)
async def test_authenticate_rejects_revoked_or_expired(
    sample_user: User, overrides: dict[str, Any]
) -> None:
    db = _db_returning(_token(sample_user, **overrides))
    assert await api_tokens.authenticate(db, "lcb_pat_secret") is None


@pytest.mark.asyncio
async def test_authenticate_rejects_unknown_token() -> None:
    assert await api_tokens.authenticate(_db_returning(None), "lcb_pat_unknown") is None


@pytest.mark.asyncio
async def test_revoke_sets_revoked_at_and_audits(sample_user: User) -> None:
    token = _token(sample_user)
    db = _db_returning()
    await api_tokens.revoke(db, sample_user, token)

    assert token.revoked_at is not None
    [entry] = _audit_entries(db)
    assert entry.action == "revoke"
    assert entry.before_state is not None and entry.before_state["revokedAt"] is None
    assert entry.after_state is not None and entry.after_state["revokedAt"] is not None


@pytest.mark.asyncio
async def test_revoke_twice_conflicts(sample_user: User) -> None:
    token = _token(sample_user, revoked_at=datetime.now(UTC))
    with pytest.raises(HTTPException) as exc_info:
        await api_tokens.revoke(_db_returning(), sample_user, token)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_get_for_user_hides_other_users_tokens(sample_user: User) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await api_tokens.get_for_user(_db_returning(None), sample_user, uuid.uuid4())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_auth_context_resolves_api_token_owner(sample_user: User) -> None:
    token = _token(sample_user)
    db = _db_returning(token, sample_user)
    context = await get_auth_context(api_tokens.TOKEN_PREFIX + "secret", db)
    assert context.user is sample_user and context.api_token is token


@pytest.mark.asyncio
async def test_auth_context_rejects_invalid_api_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_auth_context(api_tokens.TOKEN_PREFIX + "secret", _db_returning(None))
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_context_rejects_token_of_inactive_user(sample_user: User) -> None:
    sample_user.is_active = False
    db = _db_returning(_token(sample_user), sample_user)
    with pytest.raises(HTTPException) as exc_info:
        await get_auth_context(api_tokens.TOKEN_PREFIX + "secret", db)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_context_still_accepts_login_jwt(sample_user: User) -> None:
    db = _db_returning(sample_user)
    context = await get_auth_context(create_access_token(str(sample_user.id)), db)
    assert context.user is sample_user and context.api_token is None


@pytest.mark.asyncio
async def test_interactive_session_refuses_api_token(sample_user: User) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_interactive_session(AuthContext(sample_user, _token(sample_user)))
    assert exc_info.value.status_code == 403
    assert await require_interactive_session(AuthContext(sample_user)) is sample_user
