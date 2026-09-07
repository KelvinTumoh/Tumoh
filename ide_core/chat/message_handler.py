"""Persist and route chat messages through the unified integration layer."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from ide_core.config.settings import IDESettings
from ide_core.llm.web_search import WebSearchClient

from .integration import UnifiedChatIntegration
from .models import ChatContext, ChatMessage, MessageType, _now_iso

if TYPE_CHECKING:
    from ide_core.llm.unified_client import UnifiedLLMClient


class MessageHandler:
    """Store chat history and convert incoming messages into reply events."""

    def __init__(
        self,
        settings: IDESettings | None = None,
        integration: UnifiedChatIntegration | None = None,
        llm_client: UnifiedLLMClient | None = None,
        storage_root: Path | None = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._root = storage_root or Path("data/chat")
        self._limit = self._settings.chat_message_history_limit

        # Existing integration path is kept for backwards compatibility / tests.
        # The unified LLM client is created on first use so missing optional
        # providers do not break startup when chat is not actually used.
        self._integration = integration
        self._llm_client = llm_client

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

    def _build_messages(
        self,
        history: list[ChatMessage],
    ) -> list[dict[str, str]]:
        """Convert stored history into an OpenAI-style message list."""
        messages: list[dict[str, str]] = []
        for msg in history:
            if msg.sender_id == "assistant":
                role = "assistant"
            elif msg.sender_id == "system":
                role = "system"
            else:
                role = "user"
            messages.append({"role": role, "content": msg.content})
        return messages

    async def _llm_reply(
        self,
        message: ChatMessage,
        context: ChatContext,
    ) -> ChatMessage:
        """Generate a reply using the smart-routing unified LLM client."""
        if self._llm_client is None:
            from ide_core.llm.unified_client import UnifiedLLMClient

            self._llm_client = UnifiedLLMClient(self._settings)

        attachment_type: str | None = None
        if message.attachments:
            attachment_type = message.attachments[0].get("type") or message.attachments[
                0
            ].get("mime_type")

        user_input = message.content
        used_web_search = False
        if WebSearchClient.is_current_event_query(message.content):
            search_client = WebSearchClient()
            search_context = await asyncio.to_thread(search_client.search, message.content)
            if search_context:
                used_web_search = True
                user_input = (
                    f"{message.content}\n\n"
                    f"Use the following real-time web search results to answer; "
                    f"if they are not enough, say you cannot find current data:\n\n"
                    f"{search_context}"
                )

        response = await self._llm_client.chat_completion(
            messages=self._build_messages(context.history),
            user_input=user_input,
            has_attachments=bool(message.attachments),
            attachment_type=attachment_type,
            attachments=message.attachments,
        )

        metadata = {
            "model": response.get("model"),
            "reason": response.get("reason"),
            "web_search": used_web_search,
        }
        if response.get("finish_reason") is not None:
            metadata["finish_reason"] = response["finish_reason"]
        if response.get("usage") is not None:
            metadata["usage"] = response["usage"]

        return ChatMessage(
            message_id=uuid.uuid4().hex,
            room_id=message.room_id,
            tenant_id=message.tenant_id,
            sender_id="Tumoh",
            type=MessageType.SYSTEM,
            content=response.get("content", ""),
            timestamp=_now_iso(),
            metadata=metadata,
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

        if self._integration is not None:
            replies = await self._integration.route(message, context)
        else:
            replies = [await self._llm_reply(message, context)]

        for reply in replies:
            self._persist(reply)
        return [message, *replies]
