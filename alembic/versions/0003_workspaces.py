"""Workspaces and per-workspace memberships.

Replaces the free-form ``X-LabChain-Workspace`` string with a real tenant table and moves
the user role from ``users.role`` to ``workspace_memberships.role``.

Data migration:
- one ``workspaces`` row per distinct workspace value already present in domain tables or
  the audit trail (slug = name = existing value);
- one membership per (user, workspace) pair found in the audit trail, with the user's
  former global role. Users with no audit activity get no membership and must be added
  by a workspace lead.

Revision ID: 0003_workspaces
Revises: 0002_audit_immutability
Create Date: 2026-11-25 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_workspaces"
down_revision: str | None = "0002_audit_immutability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = postgresql.ENUM(
    "bioinformatics_lead", "lab_technician", name="user_role", create_type=False
)

TENANT_TABLES = (
    "samples",
    "sequencing_runs",
    "fastq_files",
    "pipeline_jobs",
    "run_output_files",
)


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_workspaces_slug", "workspaces", ["slug"], unique=True)

    op.create_table(
        "workspace_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", user_role, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_membership"),
    )
    op.create_index(
        "ix_workspace_memberships_workspace_id", "workspace_memberships", ["workspace_id"]
    )
    op.create_index("ix_workspace_memberships_user_id", "workspace_memberships", ["user_id"])

    # --- data migration -----------------------------------------------------------------
    sources = " UNION ".join(
        f"SELECT workspace FROM {table}" for table in (*TENANT_TABLES, "audit_logs")
    )
    op.execute(
        f"""
        INSERT INTO workspaces (id, slug, name)
        SELECT gen_random_uuid(), w.workspace, w.workspace
        FROM ({sources}) AS w
        WHERE w.workspace IS NOT NULL AND btrim(w.workspace) <> ''
        GROUP BY w.workspace
        """
    )
    op.execute(
        """
        INSERT INTO workspace_memberships (id, workspace_id, user_id, role)
        SELECT gen_random_uuid(), w.id, u.id, u.role
        FROM (SELECT DISTINCT actor_id, workspace FROM audit_logs
              WHERE actor_id IS NOT NULL AND workspace IS NOT NULL) AS a
        JOIN users u ON u.id = a.actor_id
        JOIN workspaces w ON w.slug = a.workspace
        """
    )

    # User-level events (login/logout/registration) are not tied to a workspace.
    # ALTER COLUMN does not fire the row-level immutability triggers from 0002.
    op.alter_column("audit_logs", "workspace", existing_type=sa.String(128), nullable=True)

    for table in TENANT_TABLES:
        op.create_foreign_key(f"fk_{table}_workspace", table, "workspaces", ["workspace"], ["slug"])

    op.drop_column("users", "role")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", user_role, nullable=False, server_default="lab_technician"),
    )
    op.execute(
        """
        UPDATE users u SET role = 'bioinformatics_lead'
        WHERE EXISTS (SELECT 1 FROM workspace_memberships m
                      WHERE m.user_id = u.id AND m.role = 'bioinformatics_lead')
        """
    )
    op.alter_column("users", "role", server_default=None)

    for table in TENANT_TABLES:
        op.drop_constraint(f"fk_{table}_workspace", table, type_="foreignkey")

    # audit_logs.workspace stays nullable: rows written with NULL cannot be updated
    # (append-only triggers), so NOT NULL cannot be restored safely.

    op.drop_index("ix_workspace_memberships_user_id", table_name="workspace_memberships")
    op.drop_index("ix_workspace_memberships_workspace_id", table_name="workspace_memberships")
    op.drop_table("workspace_memberships")
    op.drop_index("ix_workspaces_slug", table_name="workspaces")
    op.drop_table("workspaces")
