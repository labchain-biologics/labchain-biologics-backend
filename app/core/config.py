"""Application settings loaded from environment / .env."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Titerlane Biologics API"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = Field(
        ...,
        min_length=32,
        description="JWT signing secret (HS256)",
    )
    bootstrap_registration_enabled: bool = False
    workspace_creation_enabled: bool = True
    access_token_expire_minutes: int = 60
    # Personal access tokens (scripts, CI, SDK): lifetime when the request names none, and the
    # longest lifetime a user may request. Every token expires.
    api_token_default_lifetime_days: int = Field(default=90, ge=1)
    api_token_max_lifetime_days: int = Field(default=365, ge=1)
    api_v1_prefix: str = "/api/v1"

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    database_url: str = "postgresql+asyncpg://titerlane:titerlane@localhost:5432/titerlane"

    google_client_id: str = ""

    aws_region: str = "us-east-1"
    # Unset: boto3's default credential chain (instance/task IAM role, AWS_PROFILE, ...).
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    s3_bucket: str = "titerlane-biologics"
    s3_endpoint_url: str | None = "http://localhost:4566"
    s3_presign_expire_seconds: int = 3600

    aws_batch_job_queue: str = "titerlane-nf-queue"
    aws_batch_job_definition: str = "titerlane-nf-job"
    aws_batch_enabled: bool = False
    nextflow_work_dir: str = "s3://titerlane-biologics/nextflow-work"
    # Passed to `nextflow run -profile`. With AWS Batch this is usually a profile defined in
    # the config at `nextflow_config_uri` (e.g. "awsbatch").
    nextflow_profile: str = "docker"
    nextflow_config_uri: str | None = None
    # Base URL Nextflow can reach to post weblog events back to this API, e.g.
    # "https://api.example.org". Unset: run status comes from AWS Batch polling only.
    public_api_url: str | None = None
    run_monitor_interval_seconds: int = Field(default=30, ge=5)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if value is None or value == "":
            return ["http://localhost:5173", "http://127.0.0.1:5173"]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        raise TypeError("cors_origins must be a comma-separated string or list")

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        blocked_values = {
            "change-me-to-a-long-random-secret-key-at-least-32-chars",
            "__replace_with_a_long_random_secret_key__",
            "replace-me",
        }
        normalized = value.strip().lower()
        if normalized in blocked_values:
            raise ValueError("secret_key must be explicitly configured to a strong random value")
        return value

    @property
    def is_localstack(self) -> bool:
        return bool(self.s3_endpoint_url)


@lru_cache
def get_settings() -> Settings:
    # SECRETS_DIR (e.g. /run/secrets with Docker secrets) holds one file per setting, named
    # after it (secret_key, database_url, ...). Environment variables take precedence.
    return Settings(_secrets_dir=os.environ.get("SECRETS_DIR") or None)


settings = get_settings()
