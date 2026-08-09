"""Immutable 21 CFR Part 11 audit logging engine."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.user import User


class AuditService:
    """Append-only audit writer. Never update or delete audit rows."""

    async def record(
        self,
        db: AsyncSession,
        *,
        action: str,
        entity_type: str,
        workspace: str,
        actor: User | None = None,
        entity_id: str | uuid.UUID | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        reason: str | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_id=actor.id if actor else None,
            actor_email=actor.email if actor else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            workspace=workspace,
            before_state=before_state,
            after_state=after_state,
            reason=reason,
            request_id=request_id,
            ip_address=ip_address,
        )
        db.add(entry)
        await db.flush()
        return entry


audit_service = AuditService()
