"""Unit tests for auth Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.auth import GoogleLoginRequest, LoginRequest, Token, UserRead


def test_login_request_requires_valid_email() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email="not-an-email", password="longenough")


def test_login_request_requires_min_password_length() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email="user@example.com", password="short")


def test_login_request_accepts_valid_payload() -> None:
    req = LoginRequest(email="user@example.com", password="SecurePass1")
    assert req.email == "user@example.com"
    assert req.password == "SecurePass1"


def test_google_login_accepts_camel_case_alias() -> None:
    req = GoogleLoginRequest.model_validate({"idToken": "x" * 20})
    assert req.id_token == "x" * 20


def test_token_serializes_camel_case() -> None:
    token = Token(access_token="abc", expires_in=3600)
    dumped = token.model_dump(by_alias=True)
    assert dumped == {
        "accessToken": "abc",
        "tokenType": "bearer",
        "expiresIn": 3600,
    }


def test_user_read_from_attributes() -> None:
    now = datetime.now(UTC)
    user_id = uuid.uuid4()
    read = UserRead.model_validate(
        {
            "id": user_id,
            "email": "lead@example.com",
            "full_name": "Lead User",
            "is_active": True,
            "created_at": now,
        }
    )
    dumped = read.model_dump(by_alias=True)
    assert dumped["fullName"] == "Lead User"
    assert dumped["isActive"] is True
