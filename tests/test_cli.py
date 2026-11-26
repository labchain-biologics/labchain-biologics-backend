"""``titerlane-admin`` argument handling (no database: the actions are covered in integration)."""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app import cli
from app.models.user import Role


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_password_is_never_an_argument() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["create-user", "--email", "a@b.example", "--password", "x"])
    assert exc.value.code == 2


def test_password_from_stdin_reads_one_line() -> None:
    stdin = io.StringIO("s3cret-password\nignored\n")
    assert cli._read_password(from_stdin=True, stdin=stdin) == "s3cret-password"


def test_no_prompt_without_a_terminal(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["create-user", "--email", "a@b.example"], stdin=io.StringIO(""))
    assert code == 1
    assert "use --password-stdin" in capsys.readouterr().err


def test_prompted_passwords_must_match(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter(["first-password", "other-password"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: next(answers))
    with pytest.raises(cli.InputError, match="do not match"):
        cli._read_password(from_stdin=False, stdin=_Tty())


def test_grant_membership_rejects_unknown_roles() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            ["grant-membership", "--email", "a@b.example", "--workspace", "w", "--role", "admin"]
        )


def test_role_choices_mirror_the_role_enum() -> None:
    assert set(cli.ROLE_CHOICES) == {role.value for role in Role}


def test_password_stdin_on_a_terminal_prompts_without_echo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "typed-password")
    assert cli._read_password(from_stdin=True, stdin=_Tty()) == "typed-password"


def test_help_needs_no_settings(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k not in {"SECRET_KEY", "DATABASE_URL"}}
    result = subprocess.run(
        [sys.executable, "-c", "from app.cli import run; run()", "--help"],
        cwd=tmp_path,  # no .env there
        env={**env, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "create-user" in result.stdout


def test_database_errors_are_reported_without_parameters(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*_: object) -> str:
        raise IntegrityError("INSERT ...", {"hashed_password": "$2b$secret-hash"}, Exception())

    monkeypatch.setattr(cli, "_execute", fail)
    code = cli.main(
        [
            "grant-membership",
            "--email",
            "a@b.example",
            "--workspace",
            "w",
            "--role",
            "lab_technician",
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "database operation failed (IntegrityError)" in err
    assert "secret-hash" not in err
