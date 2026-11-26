"""
The database session commits before the response is sent.

With FastAPI's default dependency scope, the code after ``yield`` in ``get_db`` (the commit)
runs once the response has already been sent: a client could use what it just created (a
personal access token, a sample) before it is committed, and a failed commit would follow a
2xx. ``deps.DbSession`` therefore uses ``scope="function"``.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import get_args
from unittest.mock import AsyncMock

from fastapi import FastAPI, params
from fastapi.testclient import TestClient

import app as app_package
from app.api.deps import DbSession
from app.core.database import get_db

APP_DIR = Path(app_package.__file__).resolve().parent


def test_session_dependency_is_function_scoped() -> None:
    depends = next(m for m in get_args(DbSession)[1:] if isinstance(m, params.Depends))
    assert depends.dependency is get_db
    assert depends.scope == "function"


def test_get_db_is_only_injected_through_db_session() -> None:
    """A bare ``Depends(get_db)`` would bring back the request scope (commit after response)."""
    offenders = [
        str(path.relative_to(APP_DIR))
        for path in APP_DIR.rglob("*.py")
        if re.search(r"Depends\(\s*get_db\s*\)", path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"use deps.DbSession instead of Depends(get_db): {offenders}"


def test_failed_commit_is_reported_instead_of_a_success() -> None:
    events: list[str] = []
    app = FastAPI()

    @app.post("/things", status_code=201)
    async def create_thing(db: DbSession) -> dict[str, bool]:
        events.append("endpoint")
        return {"created": True}

    async def failing_db() -> AsyncIterator[AsyncMock]:
        yield AsyncMock()
        events.append("commit")
        raise RuntimeError("commit failed")

    app.dependency_overrides[get_db] = failing_db
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/things")

    assert events == ["endpoint", "commit"]
    assert response.status_code == 500
