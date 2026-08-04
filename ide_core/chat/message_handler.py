"""Persist and route chat messages through the unified integration layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ide_core.config.settings import IDESettings

from .integration import UnifiedChatIntegration
from .models import ChatContext, ChatMessage, MessageType, _now_iso


class MessageHandler:
    """Store chat history and convert incoming messages into reply events."""

    def __init__(
        self,
        settings: Optional[IDESettings] = None,
        integration: Optional[UnifiedChatIntegration] = None,
        storage_root: Optional[Path] = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._integration = integration or UnifiedChatIntegration(self._settings)
        self._root = storage_root or Path("data/chat")
        self._limit = self._settings.chat_message_history_limit

    def _messages_path(self, tenant_id: str, room_id: str) -> Path:
        return self._root / tenant_id / f"messages_{room_id}.json"

    def _load_raw(self, tenant_id: str, room_id: str) -> list[dict]:
        path = self._messages_path(tenant_id, room_id)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return []

    def _load_history(self, tenant_id: str, room_id: str) -> list[ChatMessage]:
        return [ChatMessage.from_dict(d) for d in self._load_raw(tenant_id, room_id)]

    def _persist(self, message: ChatMessage) -> None:
        path = self._messages_path(message.tenant_id, message.room_id)
        history = self._load_raw(message.tenant_id, message.room_id)
        history.append(message.to_dict())
        if len(history) > self._limit:
            history = history[-self._limit :]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(history, indent=2, default=str),
            encoding="utf-8",
        )

    async def process_message(
        self, message: ChatMessage, context: ChatContext
    ) -> list[ChatMessage]:
        """Persist the incoming message, route it, and persist replies."""
        if not self._settings.enable_chat:
            disabled = ChatMessage(
                message_id=message.message_id,
                room_id=message.room_id,
                tenant_id=message.tenant_id,
                sender_id="system",
                type=MessageType.SYSTEM,
                content="Chat is currently disabled.",
                timestamp=_now_iso(),
            )
            return [message, disabled]

        self._persist(message)
        context.history = self._load_history(message.tenant_id, message.room_id)[
            -self._limit :
        ]
        replies = await self._integration.route(message, context)
        for reply in replies:
            self._persist(reply)
        return [message, *replies]
