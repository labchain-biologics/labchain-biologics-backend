"""Workspaces and their members."""

from __future__ import annotations

import builtins
import uuid

from titerlane.models import Member, MemberCreate, MemberUpdate, Role, Workspace, WorkspaceCreate
from titerlane.resources._base import Resource, parse, parse_list


class Workspaces(Resource):
    def list(self) -> builtins.list[Workspace]:
        """Workspaces you belong to, with your role in each."""
        return parse_list(Workspace, self._http.request("GET", "/workspaces", tenant=False))

    def create(self, slug: str, name: str) -> Workspace:
        """Create a workspace. You become its ``bioinformatics_lead``."""
        body = WorkspaceCreate(slug=slug, name=name).to_json()
        return parse(Workspace, self._http.request("POST", "/workspaces", tenant=False, json=body))


class Members(Resource):
    """Members of the client's workspace. Changes require the ``bioinformatics_lead`` role."""

    def list(self) -> builtins.list[Member]:
        return parse_list(Member, self._http.request("GET", "/members"))

    def add(self, email: str, role: Role | str = Role.lab_technician) -> Member:
        body = MemberCreate(email=email, role=Role(role)).to_json()
        return parse(Member, self._http.request("POST", "/members", json=body))

    def change_role(self, user_id: uuid.UUID | str, role: Role | str) -> Member:
        body = MemberUpdate(role=Role(role)).to_json()
        return parse(Member, self._http.request("PATCH", f"/members/{user_id}", json=body))

    def remove(self, user_id: uuid.UUID | str) -> None:
        self._http.request("DELETE", f"/members/{user_id}")
