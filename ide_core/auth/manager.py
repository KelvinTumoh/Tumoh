"""API key and JWT token management for the IDE engine."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Set

import jwt
from pydantic import BaseModel

from ide_core.config.settings import IDESettings


class User(BaseModel):
    """Authenticated user identity."""

    user_id: str
    name: str
    role: str = "user"
    tenant_id: Optional[str] = None


class AuthManager:
    """Verify API keys and issue/validate JWT access tokens."""

    def __init__(
        self,
        settings: Optional[IDESettings] = None,
        api_keys: Optional[Set[str]] = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._api_keys = set(api_keys or [])

    def register_key(self, key: str) -> None:
        """Register an allowed API key."""
        self._api_keys.add(key)

    def verify_api_key(self, key: str) -> bool:
        """Return ``True`` if the API key is registered and non-empty."""
        return bool(key) and key in self._api_keys

    def create_token(self, user: User) -> str:
        """Issue a JWT access token for ``user``."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user.user_id,
            "name": user.name,
            "role": user.role,
            "tenant_id": user.tenant_id,
            "iat": now,
            "exp": now + timedelta(minutes=self._settings.jwt_expiry_minutes),
        }
        return jwt.encode(
            payload,
            self._settings.jwt_secret,
            algorithm=self._settings.jwt_algorithm,
        )

    def verify_token(self, token: str) -> Optional[User]:
        """Validate a token and return the ``User`` it represents."""
        try:
            payload = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=[self._settings.jwt_algorithm],
            )
            return User(
                user_id=payload["sub"],
                name=payload["name"],
                role=payload.get("role", "user"),
                tenant_id=payload.get("tenant_id"),
            )
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, KeyError):
            return None
