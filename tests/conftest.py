"""Shared fixtures for Titerlane Biologics unit tests."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-characters-long")

from app.models.user import User


@pytest.fixture
def sample_user() -> User:
    user = User(
        id=uuid.uuid4(),
        email="lead@titerlane.example",
        full_name="Bio Lead",
        hashed_password="hashed",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return user


@pytest.fixture
def lab_technician() -> User:
    return User(
        id=uuid.uuid4(),
        email="tech@titerlane.example",
        full_name="Lab Tech",
        hashed_password="hashed",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def mock_s3_client() -> MagicMock:
    client = MagicMock()
    client.generate_presigned_url.return_value = "https://s3.example/presigned"
    client.head_object.return_value = {"ContentLength": 100}
    client.head_bucket.return_value = {}
    return client


@pytest.fixture
def any_uuid() -> uuid.UUID:
    return uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture
def sample_create_payload() -> dict[str, Any]:
    return {
        "sampleCode": "S-001",
        "modality": "transcriptomics",
        "rinDin": 8.5,
        "concentrationNgUl": 120.0,
        "qcStatus": "pending",
    }
