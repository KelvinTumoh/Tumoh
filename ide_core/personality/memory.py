"""Persistent, tenant-isolated JSON storage for friend personality state."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ide_core.config.settings import IDESettings

from .models import UserState


class FriendMemory:
    """Manages per-tenant, per-user friend personality state on disk."""

    def __init__(self, settings: IDESettings | None = None) -> None:
        self._settings = settings or IDESettings()
        self._root = Path(self._settings.personality_storage_path)

    def _user_path(self, tenant_id: str, user_id: str) -> Path:
        return self._root / tenant_id / f"{user_id}.json"

    def _ensure_dirs(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}

    def _save(self, path: Path, data: dict[str, Any]) -> None:
        self._ensure_dirs(path)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _state_from_dict(
        self, tenant_id: str, user_id: str, data: dict[str, Any]
    ) -> UserState:
        data.setdefault("user_id", user_id)
        data.setdefault("tenant_id", tenant_id)
        for key, default in (
            ("greeting_count", 0),
            ("friendship_level", 1.0),
            ("last_interaction", ""),
            ("achievements", []),
            ("preferences", {}),
        ):
            data.setdefault(key, default)
        return UserState(**data)

    def _state_to_dict(self, state: UserState) -> dict[str, Any]:
        return asdict(state)

    def get_user_state(self, tenant_id: str, user_id: str) -> UserState:
        """Load (or default) the user state for a tenant/user pair."""
        path = self._user_path(tenant_id, user_id)
        data = self._load(path)
        return self._state_from_dict(tenant_id, user_id, data)

    def _save_user_state(self, tenant_id: str, user_id: str, state: UserState) -> None:
        path = self._user_path(tenant_id, user_id)
        self._save(path, self._state_to_dict(state))

    def remember_preference(
        self, tenant_id: str, user_id: str, key: str, value: Any
    ) -> None:
        """Store a user preference under the tenant/user key."""
        state = self.get_user_state(tenant_id, user_id)
        state.preferences[key] = value
        state.last_interaction = _now_iso()
        self._save_user_state(tenant_id, user_id, state)

    def get_preference(
        self, tenant_id: str, user_id: str, key: str
    ) -> Any:
        """Retrieve a stored user preference, or None if missing."""
        state = self.get_user_state(tenant_id, user_id)
        return state.preferences.get(key)

    def increment_friendship(
        self, tenant_id: str, user_id: str, delta: float = 0.1
    ) -> float:
        """Increment the friendship level and persist the new value."""
        state = self.get_user_state(tenant_id, user_id)
        state.friendship_level = min(10.0, state.friendship_level + float(delta))
        state.last_interaction = _now_iso()
        self._save_user_state(tenant_id, user_id, state)
        return state.friendship_level


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
