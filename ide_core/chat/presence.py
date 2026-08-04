"""Online presence tracking for tenant-scoped chat rooms."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from .models import ChatMessage, MessageType, _now_iso

if TYPE_CHECKING:
    from .room_manager import RoomManager


class PresenceManager:
    """Track online users and broadcast presence events per tenant/room."""

    def __init__(self, room_manager: Optional[RoomManager] = None) -> None:
        self._room_manager = room_manager
        self._online: dict[str, set[str]] = {}

    def _ensure_tenant(self, tenant_id: str) -> set[str]:
        if tenant_id not in self._online:
            self._online[tenant_id] = set()
        return self._online[tenant_id]

    def set_online(self, tenant_id: str, user_id: str) -> None:
        """Mark a user as online for the tenant."""
        self._ensure_tenant(tenant_id).add(user_id)

    def set_offline(self, tenant_id: str, user_id: str) -> None:
        """Mark a user as offline for the tenant."""
        online = self._ensure_tenant(tenant_id)
        online.discard(user_id)

    def get_online_users(self, tenant_id: str, room_id: str) -> list[str]:
        """Return online users for the given tenant and room."""
        online = self._online.get(tenant_id, set())
        if self._room_manager is None:
            return list(online)

        room = self._room_manager.get_room(tenant_id, room_id)
        if room is None:
            return []
        return [u for u in online if u in room.participants]

    def broadcast_presence(self, tenant_id: str, room_id: str) -> dict:
        """Build a presence event for the room as a serialized ``ChatMessage``."""
        online = self.get_online_users(tenant_id, room_id)
        message = ChatMessage(
            message_id=uuid.uuid4().hex,
            room_id=room_id,
            tenant_id=tenant_id,
            sender_id="system",
            type=MessageType.PRESENCE,
            content="presence",
            timestamp=_now_iso(),
            metadata={"online_users": online, "count": len(online)},
        )
        return message.to_dict()
