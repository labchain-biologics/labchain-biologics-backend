"""Current user and personal access tokens."""

from __future__ import annotations

import builtins
import uuid

from labchain.models import ApiToken, ApiTokenCreate, ApiTokenCreated, User
from labchain.resources._base import Resource, parse, parse_list


class Tokens(Resource):
    """Personal access tokens of the current user."""

    def list(self) -> builtins.list[ApiToken]:
        """Your tokens, newest first, including revoked and expired ones (never the secret)."""
        return parse_list(ApiToken, self._http.request("GET", "/auth/tokens", tenant=False))

    def create(self, name: str, *, expires_in_days: int | None = None) -> ApiTokenCreated:
        """
        Issue a token. Its secret (``.token``) is returned only now: store it safely.
        Requires a login session; a personal access token cannot create another one.
        """
        body = ApiTokenCreate(name=name, expires_in_days=expires_in_days).to_json()
        data = self._http.request("POST", "/auth/tokens", tenant=False, json=body)
        return parse(ApiTokenCreated, data)

    def revoke(self, token_id: uuid.UUID | str) -> ApiToken:
        """Revoke a token. It stops working immediately."""
        data = self._http.request("DELETE", f"/auth/tokens/{token_id}", tenant=False)
        return parse(ApiToken, data)


class Auth(Resource):
    """The current user and their tokens."""

    @property
    def tokens(self) -> Tokens:
        return Tokens(self._http)

    def me(self) -> User:
        """The current user and their workspaces, with their role in each."""
        return parse(User, self._http.request("GET", "/auth/me", tenant=False))

    def logout(self) -> None:
        """Record a logout in the audit trail. The credential itself is not invalidated."""
        self._http.request("POST", "/auth/logout", tenant=False)
