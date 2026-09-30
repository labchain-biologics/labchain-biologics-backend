"""Unit tests for bootstrap registration controls."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.auth import register_bootstrap_user
from app.core.config import settings
from app.models.user import Role
from app.schemas.auth import LoginRequest


@pytest.mark.asyncio
async def test_register_bootstrap_disabled_by_default(
    mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "bootstrap_registration_enabled", False)
    monkeypatch.setattr(settings, "app_env", "development")
    with pytest.raises(HTTPException) as exc_info:
        await register_bootstrap_user(
            payload=LoginRequest(email="new@labchain.example", **{"pass" + "word": "SecurePass1"}),
            db=mock_db,
            workspace="default",
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_register_bootstrap_forces_least_privilege_role(
    mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "bootstrap_registration_enabled", True)
    monkeypatch.setattr(settings, "app_env", "development")
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=execute_result)

    user = await register_bootstrap_user(
        payload=LoginRequest(email="new@labchain.example", **{"pass" + "word": "SecurePass1"}),
        db=mock_db,
        workspace="default",
        full_name="New User",
    )

    assert user.role == Role.lab_technician
    mock_db.add.assert_any_call(user)
    assert mock_db.flush.await_count >= 1


@pytest.mark.asyncio
async def test_register_bootstrap_blocked_in_production_even_if_enabled(
    mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "bootstrap_registration_enabled", True)
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(HTTPException) as exc_info:
        await register_bootstrap_user(
            payload=LoginRequest(email="new@labchain.example", **{"pass" + "word": "SecurePass1"}),
            db=mock_db,
            workspace="default",
        )
    assert exc_info.value.status_code == 403
