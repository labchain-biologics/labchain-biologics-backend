"""Unit tests for FastAPI auth / RBAC dependencies."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.deps import RequireRole, get_workspace
from app.models.user import Role, User


@pytest.mark.asyncio
async def test_get_workspace_uses_header() -> None:
    assert await get_workspace("lab-west") == "lab-west"


@pytest.mark.asyncio
async def test_get_workspace_requires_header() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_workspace(None)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_workspace_rejects_blank_header() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_workspace("   ")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_require_role_allows_matching_role(sample_user: User) -> None:
    dependency = RequireRole(Role.bioinformatics_lead)
    user = await dependency(sample_user)
    assert user is sample_user


@pytest.mark.asyncio
async def test_require_role_accepts_string_role(sample_user: User) -> None:
    dependency = RequireRole("bioinformatics_lead")
    user = await dependency(sample_user)
    assert user.role == Role.bioinformatics_lead


@pytest.mark.asyncio
async def test_require_role_forbids_mismatched_role(lab_technician: User) -> None:
    dependency = RequireRole(Role.bioinformatics_lead)
    with pytest.raises(HTTPException) as exc_info:
        await dependency(lab_technician)
    assert exc_info.value.status_code == 403
    assert "lab_technician" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_require_lab_or_lead_allows_technician(lab_technician: User) -> None:
    dependency = RequireRole(Role.lab_technician, Role.bioinformatics_lead)
    user = await dependency(lab_technician)
    assert user.role == Role.lab_technician
