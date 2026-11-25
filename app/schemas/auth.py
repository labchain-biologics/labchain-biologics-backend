"""Authentication and user Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import Role


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class GoogleLoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    id_token: str = Field(alias="idToken", min_length=10)


class Token(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    access_token: str = Field(alias="accessToken")
    token_type: str = Field(default="bearer", alias="tokenType")
    expires_in: int = Field(alias="expiresIn")


class UserRead(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True,
        populate_by_name=True,
        from_attributes=True,
    )

    id: uuid.UUID
    email: EmailStr
    full_name: str = Field(alias="fullName")
    is_active: bool = Field(alias="isActive")
    created_at: datetime = Field(alias="createdAt")


class LogoutResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    detail: str = "Successfully logged out"


class MembershipSummary(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    workspace_id: uuid.UUID = Field(alias="workspaceId")
    slug: str
    name: str
    role: Role


class UserMe(UserRead):
    memberships: list[MembershipSummary] = Field(default_factory=list)
