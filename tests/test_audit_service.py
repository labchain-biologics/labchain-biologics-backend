"""Unit tests for append-only audit service."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.audit import AuditLog
from app.models.user import User
from app.services.audit_service import AuditService


@pytest.mark.asyncio
async def test_record_appends_audit_entry(mock_db: AsyncMock, sample_user: User) -> None:
    service = AuditService()
    entity_id = uuid.uuid4()

    entry = await service.record(
        mock_db,
        action="sample.create",
        entity_type="sample",
        workspace="default",
        actor=sample_user,
        entity_id=entity_id,
        before_state=None,
        after_state={"sampleCode": "S-001"},
        reason="intake",
        request_id="req-1",
        ip_address="127.0.0.1",
    )

    assert isinstance(entry, AuditLog)
    assert entry.actor_id == sample_user.id
    assert entry.actor_email == sample_user.email
    assert entry.action == "sample.create"
    assert entry.entity_type == "sample"
    assert entry.entity_id == str(entity_id)
    assert entry.workspace == "default"
    assert entry.after_state == {"sampleCode": "S-001"}
    assert entry.reason == "intake"
    assert entry.request_id == "req-1"
    assert entry.ip_address == "127.0.0.1"
    mock_db.add.assert_called_once_with(entry)
    mock_db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_allows_anonymous_actor(mock_db: AsyncMock) -> None:
    service = AuditService()
    entry = await service.record(
        mock_db,
        action="auth.login_failed",
        entity_type="user",
        workspace="default",
        actor=None,
    )
    assert entry.actor_id is None
    assert entry.actor_email is None
    mock_db.add.assert_called_once()


@pytest.mark.asyncio
async def test_record_is_append_only(mock_db: AsyncMock) -> None:
    """Audit trail is append-only: only add + flush, never merge/delete."""
    mock_db.merge = MagicMock()
    mock_db.delete = MagicMock()
    service = AuditService()
    await service.record(
        mock_db,
        action="sample.update",
        entity_type="sample",
        workspace="ws",
    )
    mock_db.add.assert_called_once()
    mock_db.flush.assert_awaited_once()
    mock_db.merge.assert_not_called()
    mock_db.delete.assert_not_called()
