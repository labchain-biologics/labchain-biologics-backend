"""Operator commands (``titerlane-admin``) against the real database: effects and audit."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.audit import AuditLog
from app.models.user import Role, User
from app.models.workspace import Workspace, WorkspaceMembership
from app.services import operator
from app.services.operator import CREATE_USER_REASON, GRANT_REASON, OperatorError

PASSWORD = "operator-password-1"

Factory = async_sessionmaker[AsyncSession]
MakeUser = Callable[..., Awaitable[User]]


async def _audit(factory: Factory, entity_type: str) -> list[AuditLog]:
    async with factory() as db:
        rows = await db.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type)
            .order_by(AuditLog.created_at)
        )
        return list(rows)


async def test_create_user_can_log_in_and_is_audited(
    session_factory: Factory, client: httpx.AsyncClient
) -> None:
    async with session_factory() as db, db.begin():
        user = await operator.create_user(
            db, email="Lead@Lab.Example", password=PASSWORD, full_name=" Lab Lead "
        )
    assert user.email == "lead@lab.example"
    assert user.full_name == "Lab Lead"

    login = await client.post(
        "/api/v1/auth/login", json={"email": "lead@lab.example", "password": PASSWORD}
    )
    assert login.status_code == 200, login.text

    entry, login_entry = await _audit(session_factory, "user")
    assert login_entry.action == "login"
    assert (entry.action, entry.actor_id, entry.reason) == ("create", None, CREATE_USER_REASON)
    assert entry.after_state == {"email": "lead@lab.example", "fullName": "Lab Lead"}
    assert PASSWORD not in str(entry.after_state)


@pytest.mark.parametrize(
    ("email", "password", "message"),
    [("not-an-email", PASSWORD, "Invalid email"), ("a@lab.example", "short", "Invalid password")],
)
async def test_create_user_validates_like_the_api(
    session_factory: Factory, email: str, password: str, message: str
) -> None:
    async with session_factory() as db:
        with pytest.raises(OperatorError, match=message):
            await operator.create_user(db, email=email, password=password, full_name="")
    assert await _audit(session_factory, "user") == []


async def test_create_user_refuses_an_existing_email(
    session_factory: Factory, make_user: MakeUser
) -> None:
    await make_user("taken@lab.example")
    async with session_factory() as db:
        with pytest.raises(OperatorError, match="already exists"):
            await operator.create_user(
                db, email="TAKEN@lab.example", password=PASSWORD, full_name=""
            )


async def test_grant_membership_creates_workspace_and_changes_role(
    session_factory: Factory, make_user: MakeUser
) -> None:
    user = await make_user("tech@lab.example")
    async with session_factory() as db, db.begin():
        first = await operator.grant_membership(
            db,
            email="tech@lab.example",
            workspace_slug="helix",
            role=Role.lab_technician,
            create_workspace=True,
            workspace_name="Helix Genomics",
        )
    assert (first.created_workspace, first.changed) == (True, True)

    async with session_factory() as db, db.begin():
        again = await operator.grant_membership(
            db, email="tech@lab.example", workspace_slug="helix", role=Role.lab_technician
        )
        promoted = await operator.grant_membership(
            db, email="tech@lab.example", workspace_slug="helix", role=Role.bioinformatics_lead
        )
    assert again.changed is False
    assert promoted.changed is True

    async with session_factory() as db:
        workspace = await db.scalar(select(Workspace).where(Workspace.slug == "helix"))
        assert workspace is not None and workspace.name == "Helix Genomics"
        membership = await db.scalar(
            select(WorkspaceMembership).where(WorkspaceMembership.user_id == user.id)
        )
        assert membership is not None and membership.role is Role.bioinformatics_lead

    memberships = await _audit(session_factory, "workspace_membership")
    assert [(e.action, e.before_state) for e in memberships] == [
        ("add_member", None),
        (
            "change_role",
            {"userId": str(user.id), "email": "tech@lab.example", "role": "lab_technician"},
        ),
    ]
    assert memberships[-1].after_state == {
        "userId": str(user.id),
        "email": "tech@lab.example",
        "role": "bioinformatics_lead",
    }
    assert all(e.reason == GRANT_REASON and e.workspace == "helix" for e in memberships)
    assert [e.action for e in await _audit(session_factory, "workspace")] == ["create"]


async def test_grant_membership_needs_existing_user_and_workspace(
    session_factory: Factory, make_user: MakeUser
) -> None:
    await make_user("tech@lab.example")
    async with session_factory() as db:
        with pytest.raises(OperatorError, match="No user"):
            await operator.grant_membership(
                db, email="nobody@lab.example", workspace_slug="helix", role=Role.lab_technician
            )
        with pytest.raises(OperatorError, match="pass --create"):
            await operator.grant_membership(
                db, email="tech@lab.example", workspace_slug="helix", role=Role.lab_technician
            )
    async with session_factory() as db:
        assert await db.scalar(select(User).where(User.email == "nobody@lab.example")) is None


async def test_grant_membership_keeps_a_lead(session_factory: Factory, make_user: MakeUser) -> None:
    await make_user("lead@lab.example")
    await make_user("other@lab.example")
    async with session_factory() as db, db.begin():
        await operator.grant_membership(
            db,
            email="lead@lab.example",
            workspace_slug="helix",
            role=Role.bioinformatics_lead,
            create_workspace=True,
        )
    async with session_factory() as db:
        with pytest.raises(OperatorError, match="only bioinformatics_lead"):
            await operator.grant_membership(
                db, email="lead@lab.example", workspace_slug="helix", role=Role.lab_technician
            )
    async with session_factory() as db, db.begin():
        await operator.grant_membership(
            db, email="other@lab.example", workspace_slug="helix", role=Role.bioinformatics_lead
        )
        demoted = await operator.grant_membership(
            db, email="lead@lab.example", workspace_slug="helix", role=Role.lab_technician
        )
    assert demoted.changed is True


@pytest.mark.parametrize(
    ("slug", "name"),
    [("lab/east", None), ("Helix", None), ("a" * 65, None), ("helix", "n" * 256)],
)
async def test_created_workspaces_follow_the_api_rules(
    session_factory: Factory, make_user: MakeUser, slug: str, name: str | None
) -> None:
    await make_user("tech@lab.example")
    async with session_factory() as db:
        with pytest.raises(OperatorError, match="Invalid workspace"):
            await operator.grant_membership(
                db,
                email="tech@lab.example",
                workspace_slug=slug,
                role=Role.lab_technician,
                create_workspace=True,
                workspace_name=name,
            )
    assert await _audit(session_factory, "workspace") == []


async def test_create_user_limits_the_full_name(session_factory: Factory) -> None:
    async with session_factory() as db:
        with pytest.raises(OperatorError, match="at most 255"):
            await operator.create_user(
                db, email="a@lab.example", password=PASSWORD, full_name="n" * 256
            )


async def test_grant_membership_refuses_deactivated_users_and_workspaces(
    session_factory: Factory, make_user: MakeUser
) -> None:
    await make_user("gone@lab.example", active=False)
    await make_user("tech@lab.example")
    async with session_factory() as db, db.begin():
        db.add(Workspace(slug="old-lab", name="Old lab", is_active=False))
    async with session_factory() as db:
        with pytest.raises(OperatorError, match="User gone@lab.example is deactivated"):
            await operator.grant_membership(
                db,
                email="gone@lab.example",
                workspace_slug="helix",
                role=Role.lab_technician,
                create_workspace=True,
            )
        with pytest.raises(OperatorError, match="'old-lab' is deactivated"):
            await operator.grant_membership(
                db, email="tech@lab.example", workspace_slug="old-lab", role=Role.lab_technician
            )
    assert await _audit(session_factory, "workspace_membership") == []
    assert await _audit(session_factory, "workspace") == []
