"""
Integration fixtures: the real FastAPI app against a real PostgreSQL database.

The database comes from ``TEST_DATABASE_URL`` (default: the docker compose Postgres on
port 5433, database ``labchain_test``). It is created if missing and migrated to head once
per session. Tables are truncated before each test. When Postgres is unreachable the
integration tests are skipped, so ``uv run poe test`` keeps working without Docker.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import asyncpg  # type: ignore[import-untyped]
import httpx
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models.user import Role, User
from app.models.workspace import Workspace, WorkspaceMembership
from app.services import batch
from app.services.s3 import ObjectChecksum, StoredObject, s3_service

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://labchain:labchain@localhost:5433/labchain_test",
)
PASSWORD = "IntegrationPass1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

TRUNCATE_SQL = (
    "TRUNCATE run_output_files, pipeline_jobs, fastq_files, sequencing_runs, samples, "
    "workspace_memberships, workspaces, audit_logs, users RESTART IDENTITY CASCADE"
)


async def _ensure_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    admin = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database="postgres",
        timeout=3,
    )
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database)
        if not exists:
            await admin.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await admin.close()


@pytest.fixture(scope="session")
def migrated_database() -> str:
    try:
        asyncio.run(_ensure_database())
    except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
        pytest.skip(f"PostgreSQL not reachable for integration tests: {exc}")
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    return TEST_DATABASE_URL


@pytest.fixture
async def session_factory(
    migrated_database: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(TRUNCATE_SQL)
    yield async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def make_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., Awaitable[User]]:
    async def _make_user(email: str, *, active: bool = True) -> User:
        async with session_factory() as session:
            user = User(
                email=email,
                full_name=email.split("@")[0],
                hashed_password=hash_password(PASSWORD),
                is_active=active,
            )
            session.add(user)
            await session.commit()
            return user

    return _make_user


@pytest.fixture
def make_workspace(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., Awaitable[Workspace]]:
    async def _make_workspace(slug: str, members: dict[uuid.UUID, Role]) -> Workspace:
        async with session_factory() as session:
            workspace = Workspace(slug=slug, name=slug.title(), is_active=True)
            session.add(workspace)
            await session.flush()
            for user_id, role in members.items():
                session.add(
                    WorkspaceMembership(workspace_id=workspace.id, user_id=user_id, role=role)
                )
            await session.commit()
            return workspace

    return _make_workspace


@pytest.fixture
def login(client: httpx.AsyncClient) -> Callable[[str], Awaitable[dict[str, str]]]:
    async def _login(email: str) -> dict[str, str]:
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['accessToken']}"}

    return _login


class FakeS3:
    """In-memory stand-in for the S3 operations the API performs (no network in tests)."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_listing = False

    @staticmethod
    def _etag(data: bytes) -> str:
        # Content-derived, like a single-part S3 ETag: replacing the bytes changes it.
        return hashlib.md5(data).hexdigest()

    def put_text(self, key: str, body: str, *, content_type: str = "text/plain") -> str:
        self.objects[key] = body.encode("utf-8")
        return f"s3://test-bucket/{key}"

    def object_checksum(self, key: str) -> ObjectChecksum | None:
        data = self.objects.get(key)
        if data is None:
            return None
        return ObjectChecksum(
            md5=hashlib.md5(data).hexdigest(), size_bytes=len(data), etag=self._etag(data)
        )

    def current_etag(self, key: str) -> str | None:
        data = self.objects.get(key)
        return None if data is None else self._etag(data)

    def list_objects(self, prefix: str) -> list[StoredObject]:
        if self.fail_listing:
            raise ConnectionError("S3 listing unavailable")
        return [
            StoredObject(key=key, size_bytes=len(data))
            for key, data in sorted(self.objects.items())
            if key.startswith(prefix)
        ]

    def uri(self, key: str) -> str:
        return f"s3://test-bucket/{key}"

    def key_from_uri(self, uri: str) -> str:
        return uri.removeprefix("s3://test-bucket/")


@pytest.fixture
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> FakeS3:
    fake = FakeS3()
    for name in (
        "put_text",
        "object_checksum",
        "current_etag",
        "list_objects",
        "uri",
        "key_from_uri",
    ):
        monkeypatch.setattr(s3_service, name, getattr(fake, name))
    monkeypatch.setattr(
        s3_service,
        "generate_presigned_upload_url",
        lambda key, **_: f"https://upload.test/{key}",
    )
    monkeypatch.setattr(
        s3_service,
        "generate_presigned_download_url",
        lambda key, **_: f"https://download.test/{key}",
    )
    return fake


@pytest.fixture(autouse=True)
def no_real_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Integration tests never reach AWS Batch or call back a real URL, whatever .env says."""
    monkeypatch.setattr(batch, "get_batch_client", lambda: None)
    monkeypatch.setattr(settings, "public_api_url", None)
