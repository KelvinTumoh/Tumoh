"""Pydantic data models for multi-tenant workspace isolation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class Tenant(BaseModel):
    """An isolated workspace tenant."""

    tenant_id: str
    name: str
    subdomain: str
    plan: Literal["free", "pro", "enterprise"] = "free"
    is_active: bool = True
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    settings: dict = Field(default_factory=dict)


class User(BaseModel):
    """A user account scoped to a tenant."""

    user_id: str
    username: str
    email: str
    tenant_id: str
    role: Literal["owner", "admin", "member"] = "member"
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Team(BaseModel):
    """A team within a tenant."""

    team_id: str
    tenant_id: str
    name: str
    member_ids: list[str] = Field(default_factory=list)


class Invitation(BaseModel):
    """An invitation to join a tenant."""

    invite_id: str
    tenant_id: str
    email: str
    role: Literal["owner", "admin", "member"] = "member"
    expires_at: datetime | None = None
