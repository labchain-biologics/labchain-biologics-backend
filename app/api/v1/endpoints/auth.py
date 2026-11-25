"""Authentication endpoints: password login, Google ID token, me, logout."""

from __future__ import annotations

import logging
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, HTTPException, Query, Request, status
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.schemas.auth import (
    GoogleLoginRequest,
    LoginRequest,
    LogoutResponse,
    MembershipSummary,
    Token,
    UserMe,
    UserRead,
)
from app.services.audit_service import audit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_google_jwk_client: PyJWKClient | None = None


def _get_google_jwk_client() -> PyJWKClient:
    global _google_jwk_client
    if _google_jwk_client is None:
        _google_jwk_client = PyJWKClient(GOOGLE_JWKS_URL)
    return _google_jwk_client


def _issue_token(user: User) -> Token:
    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"email": user.email},
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


async def _authenticate_password(db: DbSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if (
        user is None
        or user.hashed_password is None
        or not verify_password(password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    return user


async def _verify_google_id_token(id_token: str) -> dict[str, Any]:
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured (GOOGLE_CLIENT_ID missing)",
        )
    try:
        signing_key = _get_google_jwk_client().get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.google_client_id,
            issuer=["accounts.google.com", "https://accounts.google.com"],
        )
    except (PyJWTError, PyJWKClientError, ValueError, TypeError) as exc:
        logger.warning("Google ID token verification failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google ID token",
        ) from exc

    if not claims.get("email") or claims.get("email_verified") is not True:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google token missing a verified email claim",
        )
    return claims


async def _get_or_create_google_user(db: DbSession, claims: dict[str, Any]) -> User:
    email = str(claims["email"]).lower()
    google_sub = str(claims["sub"])
    full_name = str(claims.get("name") or claims.get("email") or "")

    result = await db.execute(
        select(User).where((User.google_sub == google_sub) | (User.email == email))
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            google_sub=google_sub,
            hashed_password=None,
            is_active=True,
        )
        db.add(user)
        await db.flush()
    else:
        if user.google_sub is None:
            user.google_sub = google_sub
        if full_name and not user.full_name:
            user.full_name = full_name
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
            )
        await db.flush()
    return user


_LOGIN_REQUEST_BODY: dict[str, Any] = {
    "required": True,
    "content": {
        "application/json": {
            "schema": {
                "oneOf": [
                    {"$ref": "#/components/schemas/LoginRequest"},
                    GoogleLoginRequest.model_json_schema(by_alias=True),
                ]
            }
        },
        "application/x-www-form-urlencoded": {
            "schema": {
                "type": "object",
                "required": ["username", "password"],
                "properties": {
                    "username": {"type": "string", "format": "email"},
                    "password": {"type": "string"},
                },
            }
        },
    },
}


@router.post("/login", response_model=Token, openapi_extra={"requestBody": _LOGIN_REQUEST_BODY})
async def login(
    request: Request,
    db: DbSession,
    provider: Annotated[str | None, Query()] = None,
) -> Token:
    """
    Authenticate with email/password JSON body, OAuth2 form, or Google ID token.

    - Default: JSON ``LoginRequest`` body
    - ``?provider=google``: JSON ``GoogleLoginRequest`` with ``idToken``
    - ``application/x-www-form-urlencoded``: OAuth2 password form (Swagger)
    """
    content_type = request.headers.get("content-type", "")

    if provider == "google":
        body = await request.json()
        google_payload = GoogleLoginRequest.model_validate(body)
        claims = await _verify_google_id_token(google_payload.id_token)
        user = await _get_or_create_google_user(db, claims)
        await audit_service.record(
            db,
            actor=user,
            action="login",
            entity_type="user",
            entity_id=user.id,
            workspace=None,
            after_state={"provider": "google", "email": user.email},
            ip_address=request.client.host if request.client else None,
        )
        return _issue_token(user)

    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        username = str(form.get("username") or "")
        password = str(form.get("password") or "")
        if not username or not password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="username and password are required",
            )
        user = await _authenticate_password(db, username.lower(), password)
    else:
        body = await request.json()
        login_payload = LoginRequest.model_validate(body)
        user = await _authenticate_password(db, login_payload.email.lower(), login_payload.password)

    await audit_service.record(
        db,
        actor=user,
        action="login",
        entity_type="user",
        entity_id=user.id,
        workspace=None,
        after_state={"provider": "password", "email": user.email},
        ip_address=request.client.host if request.client else None,
    )
    return _issue_token(user)


@router.get("/me", response_model=UserMe)
async def read_me(current_user: CurrentUser, db: DbSession) -> UserMe:
    """Current user and the workspaces they belong to, with their role in each."""
    result = await db.execute(
        select(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == current_user.id)
        .options(selectinload(WorkspaceMembership.workspace))
    )
    memberships = [
        MembershipSummary(
            workspace_id=membership.workspace.id,
            slug=membership.workspace.slug,
            name=membership.workspace.name,
            role=membership.role,
        )
        for membership in result.scalars().all()
        if membership.workspace.is_active
    ]
    memberships.sort(key=lambda item: item.name.lower())
    return UserMe(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        memberships=memberships,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> LogoutResponse:
    await audit_service.record(
        db,
        actor=current_user,
        action="logout",
        entity_type="user",
        entity_id=current_user.id,
        workspace=None,
        ip_address=request.client.host if request.client else None,
    )
    return LogoutResponse()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_bootstrap_user(
    payload: LoginRequest,
    db: DbSession,
    full_name: Annotated[str, Query(alias="fullName")] = "",
) -> User:
    """
    Bootstrap user registration for local/dev environments.
    Disabled when APP_ENV=production. The new user belongs to no workspace: they create one
    (``POST /workspaces``) or are added to one by a workspace lead.
    """
    if settings.app_env == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-registration is disabled in production",
        )
    if not settings.bootstrap_registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bootstrap registration is not enabled",
        )

    existing = await db.execute(select(User).where(User.email == payload.email.lower()))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=payload.email.lower(),
        full_name=full_name or payload.email.split("@")[0],
        hashed_password=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await audit_service.record(
        db,
        actor=user,
        action="register",
        entity_type="user",
        entity_id=user.id,
        workspace=None,
        after_state={"email": user.email},
    )
    return user
