"""Persistent, tenant-isolated chat room storage."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

from ide_core.config.settings import IDESettings

from .models import ChatRoom, _now_iso


class RoomManager:
    """Manage chat rooms stored as JSON inside ``data/chat/<tenant_id>/rooms.json``."""

    def __init__(
        self,
        settings: Optional[IDESettings] = None,
        storage_root: Optional[Path] = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._root = storage_root or Path("data/chat")

    def _tenant_dir(self, tenant_id: str) -> Path:
        """Return (and create if needed) the per-tenant chat directory."""
        path = self._root / tenant_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _rooms_path(self, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "rooms.json"

    def _load(self, tenant_id: str) -> list[ChatRoom]:
        path = self._rooms_path(tenant_id)
        if not path.exists():
            return []
        try:
            return [ChatRoom.from_dict(d) for d in json.loads(path.read_text())]
        except (json.JSONDecodeError, ValueError):
            return []

    def _save(self, tenant_id: str, rooms: list[ChatRoom]) -> None:
        path = self._rooms_path(tenant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([r.to_dict() for r in rooms], indent=2), encoding="utf-8"
        )

    def create_room(
        self, tenant_id: str, name: str, participants: list[str]
    ) -> ChatRoom:
        """Create a new room and persist it under the tenant."""
        room = ChatRoom(
            room_id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            name=name,
            participants=list(participants),
            created_at=_now_iso(),
        )
        rooms = self._load(tenant_id)
        rooms.append(room)
        self._save(tenant_id, rooms)
        return room

    def join_room(self, tenant_id: str, room_id: str, user_id: str) -> bool:
        """Add a user to a room's participant list."""
        rooms = self._load(tenant_id)
        for room in rooms:
            if room.room_id == room_id and user_id not in room.participants:
                room.participants.append(user_id)
                self._save(tenant_id, rooms)
                return True
        return False

    def leave_room(self, tenant_id: str, room_id: str, user_id: str) -> bool:
        """Remove a user from a room's participant list."""
        rooms = self._load(tenant_id)
        for room in rooms:
            if room.room_id == room_id and user_id in room.participants:
                room.participants.remove(user_id)
                self._save(tenant_id, rooms)
                return True
        return False

    def list_rooms(self, tenant_id: str, user_id: str) -> list[ChatRoom]:
        """Return rooms the user is in or that are public."""
        return [
            r
            for r in self._load(tenant_id)
            if user_id in r.participants or not r.is_private
        ]

    def get_room(self, tenant_id: str, room_id: str) -> Optional[ChatRoom]:
        """Return a single room by ID, or ``None`` if not found."""
        for room in self._load(tenant_id):
            if room.room_id == room_id:
                return room
        return None
