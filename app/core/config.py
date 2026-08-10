"""Application settings loaded from environment / .env."""

from __future__ import annotations

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

    app_name: str = "VesselChain Biologics API"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = Field(
        default="change-me-to-a-long-random-secret-key-at-least-32-chars",
        min_length=32,
        description="JWT signing secret (HS256)",
    )
    access_token_expire_minutes: int = 60
    api_v1_prefix: str = "/api/v1"

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    database_url: str = "postgresql+asyncpg://vesselchain:vesselchain@localhost:5432/vesselchain"

    google_client_id: str = ""

    aws_region: str = "us-east-1"
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"
    s3_bucket: str = "vesselchain-biologics"
    s3_endpoint_url: str | None = "http://localhost:4566"
    s3_presign_expire_seconds: int = 3600

    aws_batch_job_queue: str = "vesselchain-nf-queue"
    aws_batch_job_definition: str = "vesselchain-nf-job"
    aws_batch_enabled: bool = False
    nextflow_work_dir: str = "s3://vesselchain-biologics/nextflow-work"

    default_workspace: str = "default"

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

    @property
    def is_localstack(self) -> bool:
        return bool(self.s3_endpoint_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
