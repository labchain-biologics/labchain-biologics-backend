"""Operator tool: grant a user a role in a workspace (creating the workspace if asked).

Used after upgrading past migration 0003, which creates workspaces from existing data but no
memberships, and on instances where WORKSPACE_CREATION_ENABLED=false.

    uv run python scripts/grant_membership.py --email lead@lab.org --workspace helix \
        --role bioinformatics_lead [--create --name "Helix Genomics"]

The grant is written to the audit trail with no user actor and the reason "operator grant".
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.user import Role, User
from app.models.workspace import Workspace, WorkspaceMembership
from app.services.audit_service import audit_service


async def grant(email: str, slug: str, role: Role, *, create: bool, name: str | None) -> str:
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            raise SystemExit(f"No user with email {email}")
        workspace = await db.scalar(select(Workspace).where(Workspace.slug == slug))
        if workspace is None:
            if not create:
                raise SystemExit(f"No workspace '{slug}' (pass --create to create it)")
            workspace = Workspace(slug=slug, name=name or slug, is_active=True)
            db.add(workspace)
            await db.flush()
            await audit_service.record(
                db,
                action="create",
                entity_type="workspace",
                entity_id=workspace.id,
                workspace=slug,
                after_state={"slug": slug, "name": workspace.name},
                reason="operator grant",
            )
        membership = await db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace.id,
                WorkspaceMembership.user_id == user.id,
            )
        )
        before = {"role": membership.role.value} if membership else None
        if membership is None:
            membership = WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role=role)
            db.add(membership)
        else:
            membership.role = role
        await db.flush()
        await audit_service.record(
            db,
            action="add_member" if before is None else "change_role",
            entity_type="workspace_membership",
            entity_id=membership.id,
            workspace=slug,
            before_state=before,
            after_state={"userId": str(user.id), "email": user.email, "role": role.value},
            reason="operator grant",
        )
        await db.commit()
        return f"{user.email} is {role.value} in workspace '{slug}'"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--workspace", required=True, help="Workspace slug")
    parser.add_argument("--role", required=True, choices=[r.value for r in Role])
    parser.add_argument("--create", action="store_true", help="Create the workspace if missing")
    parser.add_argument("--name", help="Display name when creating the workspace")
    args = parser.parse_args()
    message = asyncio.run(
        grant(args.email, args.workspace, Role(args.role), create=args.create, name=args.name)
    )
    print(message)


if __name__ == "__main__":
    main()
