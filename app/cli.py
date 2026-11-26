"""
``titerlane-admin``: operator commands, run on the server host with the server's settings.

    titerlane-admin create-user --email lead@lab.example --full-name "Lab Lead"
    titerlane-admin grant-membership --email lead@lab.example --workspace helix \\
        --role bioinformatics_lead --create --name "Helix Genomics"

In the container image: ``docker compose run --rm api titerlane-admin ...``. Passwords are
never taken as arguments (shell history, process list): they are prompted for, or read from
standard input with ``--password-stdin``. Every action is written to the audit trail.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Mirrors app.models.user.Role (checked by tests/test_cli.py). Importing the models loads the
# settings, which `--help` and argument errors must not need.
ROLE_CHOICES = ("lab_technician", "bioinformatics_lead")


class InputError(Exception):
    """The operator's input was refused before reaching the database."""


def _read_password(*, from_stdin: bool, stdin: TextIO) -> str:
    # On a terminal, --password-stdin would echo the password: prompt without echo instead.
    if from_stdin and not stdin.isatty():
        return stdin.readline().rstrip("\r\n")
    if not stdin.isatty():
        raise InputError("No terminal to prompt for the password: use --password-stdin")
    password = getpass.getpass("Password: ")
    if getpass.getpass("Repeat password: ") != password:
        raise InputError("Passwords do not match")
    return password


async def _in_transaction(action: Callable[[AsyncSession], Awaitable[str]]) -> str:
    from app.core.database import AsyncSessionLocal, engine

    try:
        async with AsyncSessionLocal() as db, db.begin():
            return await action(db)
    finally:
        await engine.dispose()


async def _create_user(args: argparse.Namespace, password: str) -> str:
    from app.services import operator

    async def action(db: AsyncSession) -> str:
        user = await operator.create_user(
            db, email=args.email, password=password, full_name=args.full_name
        )
        return f"Created user {user.email} ({user.id})"

    return await _in_transaction(action)


async def _grant_membership(args: argparse.Namespace) -> str:
    from app.models.user import Role
    from app.services import operator

    async def action(db: AsyncSession) -> str:
        grant = await operator.grant_membership(
            db,
            email=args.email,
            workspace_slug=args.workspace,
            role=Role(args.role),
            create_workspace=args.create,
            workspace_name=args.name,
        )
        created = " (workspace created)" if grant.created_workspace else ""
        unchanged = " (unchanged)" if not grant.changed else ""
        return (
            f"{grant.email} is {grant.role.value} in workspace '{grant.workspace}'"
            f"{created}{unchanged}"
        )

    return await _in_transaction(action)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="titerlane-admin",
        description="Titerlane Biologics operator commands (audited).",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-user", help="Create a password user")
    create.add_argument("--email", required=True)
    create.add_argument("--full-name", default="", help="Display name (default: email local part)")
    create.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from the first line of standard input instead of prompting",
    )

    grant = commands.add_parser(
        "grant-membership", help="Give a user a role in a workspace (creating it if asked)"
    )
    grant.add_argument("--email", required=True)
    grant.add_argument("--workspace", required=True, help="Workspace slug")
    grant.add_argument("--role", required=True, choices=ROLE_CHOICES)
    grant.add_argument("--create", action="store_true", help="Create the workspace if missing")
    grant.add_argument("--name", help="Display name when creating the workspace")
    return parser


def _execute(args: argparse.Namespace, stdin: TextIO) -> str:
    if args.command == "create-user":
        password = _read_password(from_stdin=args.password_stdin, stdin=stdin)
        return asyncio.run(_create_user(args, password))
    return asyncio.run(_grant_membership(args))


def main(argv: Sequence[str] | None = None, *, stdin: TextIO | None = None) -> int:
    args = build_parser().parse_args(argv)
    from pydantic import ValidationError
    from sqlalchemy.exc import SQLAlchemyError

    try:
        from app.services.operator import OperatorError
    except ValidationError as exc:
        # Field names only: the values may be secrets.
        fields = ", ".join(str(error["loc"][-1]).upper() for error in exc.errors())
        print(f"Error: invalid or missing settings: {fields}", file=sys.stderr)
        return 1

    try:
        message = _execute(args, stdin or sys.stdin)
    except (InputError, OperatorError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        # Not str(exc): it can carry statement parameters such as the password hash.
        print(f"Error: database operation failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: cannot reach the database ({exc})", file=sys.stderr)
        return 1
    print(message)
    return 0


def run() -> None:
    sys.exit(main())
