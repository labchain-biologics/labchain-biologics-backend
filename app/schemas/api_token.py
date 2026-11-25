"""Personal access token Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiTokenCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    name: str = Field(
        min_length=1,
        max_length=100,
        description="What the token is for, e.g. 'CI pipeline' or 'analysis notebook'",
    )
    expires_in_days: int | None = Field(
        default=None,
        ge=1,
        alias="expiresInDays",
        description=(
            "Lifetime in days. Defaults to API_TOKEN_DEFAULT_LIFETIME_DAYS; "
            "at most API_TOKEN_MAX_LIFETIME_DAYS"
        ),
    )

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class ApiTokenRead(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True,
        populate_by_name=True,
        from_attributes=True,
    )

    id: uuid.UUID
    name: str
    token_prefix: str = Field(
        alias="tokenPrefix", description="First characters of the secret, to tell tokens apart"
    )
    created_at: datetime = Field(alias="createdAt")
    expires_at: datetime = Field(alias="expiresAt")
    last_used_at: datetime | None = Field(alias="lastUsedAt")
    revoked_at: datetime | None = Field(alias="revokedAt")


class ApiTokenCreated(ApiTokenRead):
    token: str = Field(
        description="The secret. Returned only in this response: it cannot be retrieved later"
    )
