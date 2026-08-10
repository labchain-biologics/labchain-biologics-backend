"""Unit tests for application settings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_default_cors_origins() -> None:
    settings = Settings(secret_key="x" * 32)
    assert "http://localhost:5173" in settings.cors_origins


def test_parse_cors_origins_from_comma_separated_string() -> None:
    settings = Settings(
        secret_key="x" * 32,
        cors_origins="https://app.example.com, https://staging.example.com",
    )
    assert settings.cors_origins == [
        "https://app.example.com",
        "https://staging.example.com",
    ]


def test_parse_cors_origins_from_list() -> None:
    settings = Settings(
        secret_key="x" * 32,
        cors_origins=["https://a.example", "https://b.example"],
    )
    assert settings.cors_origins == ["https://a.example", "https://b.example"]


def test_parse_cors_origins_empty_string_uses_defaults() -> None:
    settings = Settings(secret_key="x" * 32, cors_origins="")
    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_parse_cors_origins_rejects_invalid_type() -> None:
    with pytest.raises(TypeError, match="cors_origins"):
        Settings(secret_key="x" * 32, cors_origins=123)  # type: ignore[arg-type]


def test_is_localstack_true_when_endpoint_set() -> None:
    settings = Settings(secret_key="x" * 32, s3_endpoint_url="http://localhost:4566")
    assert settings.is_localstack is True


def test_is_localstack_false_when_endpoint_missing() -> None:
    settings = Settings(secret_key="x" * 32, s3_endpoint_url=None)
    assert settings.is_localstack is False


def test_secret_key_min_length_enforced() -> None:
    with pytest.raises(ValidationError):
        Settings(secret_key="too-short")
