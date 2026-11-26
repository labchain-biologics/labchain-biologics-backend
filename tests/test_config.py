"""Unit tests for application settings."""

from __future__ import annotations

from pathlib import Path

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


def test_secret_key_placeholder_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(secret_key="__replace_with_a_long_random_secret_key__")


def test_secret_key_required_when_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_aws_credentials_default_to_boto3_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    settings = Settings(_env_file=None, secret_key="x" * 32)
    assert settings.aws_access_key_id is None
    assert settings.aws_secret_access_key is None


def test_settings_read_from_secrets_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    secret = "s" * 40
    url = "postgresql+asyncpg://u:p@db:5432/titerlane"
    (tmp_path / "secret_key").write_text(secret + "\n")
    (tmp_path / "database_url").write_text(url)
    settings = Settings(_env_file=None, _secrets_dir=tmp_path)
    assert settings.secret_key == secret
    assert settings.database_url == url


def test_environment_overrides_secrets_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SECRET_KEY", "e" * 40)
    (tmp_path / "secret_key").write_text("f" * 40)
    settings = Settings(_env_file=None, _secrets_dir=tmp_path)
    assert settings.secret_key == "e" * 40
