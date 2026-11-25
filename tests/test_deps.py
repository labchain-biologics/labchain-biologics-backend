"""Unit tests for FastAPI auth / workspace membership / RBAC dependencies."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.deps import RequireRole, get_membership, get_workspace, parse_workspace_header
from app.models.user import Role, User
from app.models.workspace import Workspace, WorkspaceMembership


def _membership(user: User, role: Role, slug: str = "lab-west") -> WorkspaceMembership:
    workspace = Workspace(id=uuid.uuid4(), slug=slug, name="Lab West", is_active=True)
    membership = WorkspaceMembership(
        id=uuid.uuid4(), workspace_id=workspace.id, user_id=user.id, role=role
    )
    membership.workspace = workspace
    return membership


def test_parse_workspace_header_strips_value() -> None:
    assert parse_workspace_header("  lab-west ") == "lab-west"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_parse_workspace_header_rejects_missing_or_blank(value: str | None) -> None:
    with pytest.raises(HTTPException) as exc_info:
        parse_workspace_header(value)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_membership_returns_membership(sample_user: User) -> None:
    membership = _membership(sample_user, Role.bioinformatics_lead)
    result = MagicMock()
    result.scalar_one_or_none.return_value = membership
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    assert await get_membership("lab-west", sample_user, db) is membership


@pytest.mark.asyncio
async def test_get_membership_hides_foreign_workspace(sample_user: User) -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    with pytest.raises(HTTPException) as exc_info:
        await get_membership("someone-else", sample_user, db)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_workspace_returns_slug(sample_user: User) -> None:
    membership = _membership(sample_user, Role.lab_technician, slug="lab-east")
    assert await get_workspace(membership) == "lab-east"


@pytest.mark.asyncio
async def test_require_role_allows_matching_role(sample_user: User) -> None:
    dependency = RequireRole(Role.bioinformatics_lead)
    membership = _membership(sample_user, Role.bioinformatics_lead)
    assert await dependency(membership, sample_user) is sample_user


@pytest.mark.asyncio
async def test_require_role_accepts_string_role(sample_user: User) -> None:
    dependency = RequireRole("bioinformatics_lead")
    membership = _membership(sample_user, Role.bioinformatics_lead)
    assert await dependency(membership, sample_user) is sample_user


@pytest.mark.asyncio
async def test_require_role_uses_workspace_role(lab_technician: User) -> None:
    dependency = RequireRole(Role.bioinformatics_lead)
    membership = _membership(lab_technician, Role.lab_technician)
    with pytest.raises(HTTPException) as exc_info:
        await dependency(membership, lab_technician)
    assert exc_info.value.status_code == 403
    assert "lab_technician" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_require_lab_or_lead_allows_technician(lab_technician: User) -> None:
    dependency = RequireRole(Role.lab_technician, Role.bioinformatics_lead)
    membership = _membership(lab_technician, Role.lab_technician)
    assert await dependency(membership, lab_technician) is lab_technician
