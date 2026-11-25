"""Workspace and membership Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import Role

SLUG_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$"


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    slug: str = Field(
        min_length=1,
        max_length=64,
        pattern=SLUG_PATTERN,
        description=(
            "Lowercase letters, digits and dashes. Sent as the X-LabChain-Workspace header."
        ),
    )
    name: str = Field(min_length=1, max_length=255)


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True,
        populate_by_name=True,
        from_attributes=True,
    )

    id: uuid.UUID
    slug: str
    name: str
    role: Role = Field(description="Role of the current user in this workspace")
    created_at: datetime = Field(alias="createdAt")


class MemberCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    email: EmailStr
    role: Role = Role.lab_technician


class MemberUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    role: Role


class MemberRead(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    user_id: uuid.UUID = Field(alias="userId")
    email: EmailStr
    full_name: str = Field(alias="fullName")
    role: Role
    is_active: bool = Field(alias="isActive")
    joined_at: datetime = Field(alias="joinedAt")
