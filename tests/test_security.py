"""Unit tests for password hashing and JWT helpers."""

from __future__ import annotations

from datetime import timedelta

import jwt
import pytest
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.core.config import settings
from app.core.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_is_not_plaintext() -> None:
    hashed = hash_password("SecurePass123!")
    assert hashed != "SecurePass123!"
    assert hashed.startswith("$2")


def test_verify_password_accepts_matching_hash() -> None:
    hashed = hash_password("SecurePass123!")
    assert verify_password("SecurePass123!", hashed) is True


def test_verify_password_rejects_mismatch() -> None:
    hashed = hash_password("SecurePass123!")
    assert verify_password("wrong-password", hashed) is False


def test_create_and_decode_access_token_roundtrip() -> None:
    token = create_access_token("user-subject", extra_claims={"role": "lab_technician"})
    payload = decode_access_token(token)
    assert payload["sub"] == "user-subject"
    assert payload["role"] == "lab_technician"
    assert "exp" in payload
    assert "iat" in payload


def test_create_access_token_respects_custom_expiry() -> None:
    token = create_access_token("subject", expires_delta=timedelta(seconds=30))
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    assert payload["sub"] == "subject"


def test_decode_access_token_rejects_tampered_token() -> None:
    token = create_access_token("subject")
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered)


def test_decode_access_token_rejects_expired_token() -> None:
    token = create_access_token("subject", expires_delta=timedelta(seconds=-1))
    with pytest.raises(ExpiredSignatureError):
        decode_access_token(token)
