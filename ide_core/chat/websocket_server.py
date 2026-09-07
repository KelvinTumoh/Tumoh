"""Async WebSocket gateway for the unified chat subsystem."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

import websockets

from ide_core.auth.manager import AuthManager
from ide_core.config.settings import IDESettings

from .message_handler import MessageHandler
from .models import ChatContext, ChatMessage, MessageType, _now_iso
from .presence import PresenceManager
from .room_manager import RoomManager

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex


class ChatWebSocketServer:
    """Serve chat clients over WebSockets with multi-tenant JWT validation."""

    def __init__(
        self,
        settings: IDESettings | None = None,
        auth: AuthManager | None = None,
        message_handler: MessageHandler | None = None,
        presence: PresenceManager | None = None,
        room_manager: RoomManager | None = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._auth = auth or AuthManager(self._settings)
        self._rooms_manager = room_manager or RoomManager(self._settings)
        self._handler = message_handler or MessageHandler(
            self._settings,
        )
        self._presence = presence or PresenceManager(self._rooms_manager)
        self._rooms: dict[tuple[str, str], set[Any]] = {}
        self._users: dict[tuple[str, str], Any] = {}

    def _extract_token(self, websocket: Any, path: str) -> str | None:
        headers = getattr(websocket, "request_headers", None)
        if headers:
            auth = headers.get("Authorization") or headers.get("authorization")
            if auth:
                if auth.lower().startswith("bearer "):
                    return auth[7:]
                return auth
        if "?" in path:
            for pair in path.split("?", 1)[1].split("&"):
                if pair.startswith("token="):
                    return pair.split("=", 1)[1]
        return None

    async def _send(self, websocket: Any, payload: dict[str, Any]) -> None:
        try:
            await websocket.send(json.dumps(payload, default=str))
        except websockets.ConnectionClosed:
            pass

    async def handle_connection(self, websocket: Any, path: str) -> None:
        """Authenticate a client, then process chat messages until disconnect."""
        if not self._settings.enable_chat:
            await self._send(websocket, {"type": "error", "content": "Chat disabled"})
            return

        token = self._extract_token(websocket, path)
        user = self._auth.verify_token(token) if token else None
        if user is None:
            await self._send(websocket, {"type": "error", "content": "Unauthorized"})
            return

        websocket.tenant_id = user.tenant_id or "default"
        websocket.user_id = user.user_id
        self._users[(websocket.tenant_id, websocket.user_id)] = websocket
        self._presence.set_online(websocket.tenant_id, websocket.user_id)

        try:
            while True:
                raw = await websocket.recv()
                data = json.loads(raw)
                await self._route_message(websocket, data)
        except websockets.ConnectionClosed:
            pass
        except json.JSONDecodeError as exc:
            await self._send(
                websocket, {"type": "error", "content": f"Invalid JSON: {exc}"}
            )
        finally:
            self._users.pop((websocket.tenant_id, websocket.user_id), None)
            self._presence.set_offline(websocket.tenant_id, websocket.user_id)
            for clients in self._rooms.values():
                clients.discard(websocket)

    async def _route_message(self, websocket: Any, message_data: dict[str, Any]) -> None:
        """Route incoming WebSocket messages to the appropriate handler."""

        msg_type = message_data.get("type")
        logger.info(f"📨 Received message type: {msg_type}")

        # Handle chat messages
        if msg_type == "chat":
            room_id = message_data.get("room_id", "General")
            user_id = getattr(websocket, "user_id", message_data.get("user_id", "anonymous"))
            message_content = (message_data.get("message") or {}).get("content", "")

            if not message_content:
                await websocket.send(json.dumps({
                    "type": "error",
                    "content": "Empty message content",
                    "message": "Please provide a message"
                }))
                return

            logger.info(f"💬 Chat message from {user_id} in {room_id}: {message_content}")

            # Echo the message back to the sender.
            await websocket.send(json.dumps({
                "type": "chat",
                "room_id": room_id,
                "sender_id": user_id,
                "content": message_content,
                "timestamp": datetime.now().isoformat()
            }))

            # Route through the smart LLM client.
            try:
                message = self._extract_message(message_data, websocket.tenant_id, user_id)
                if message is None:
                    message = ChatMessage(
                        message_id=_new_id(),
                        room_id=room_id,
                        tenant_id=websocket.tenant_id,
                        sender_id=user_id,
                        type=MessageType.TEXT,
                        content=message_content,
                        timestamp=_now_iso(),
                    )

                context = ChatContext(
                    tenant_id=websocket.tenant_id,
                    user_id=user_id,
                    room_id=room_id,
                )
                replies = await self._handler.process_message(message, context)

                # replies[0] is the original message (already echoed), the rest are assistant replies.
                for reply in replies[1:]:
                    logger.info(f"🧠 Selected model: {reply.metadata.get('model')}")
                    await self._send(websocket, reply.to_dict())
                    logger.info(f"✅ Sent LLM reply to {user_id}")
            except Exception as exc:
                logger.exception("LLM processing failed for %s", user_id)
                await self._send(
                    websocket,
                    {
                        "type": "error",
                        "content": f"AI processing failed: {exc}",
                    },
                )
            return

        # Handle presence messages
        if msg_type == "presence":
            await websocket.send(json.dumps({
                "type": "presence",
                "room_id": message_data.get("room_id", "General"),
                "sender_id": "system",
                "content": "presence",
                "timestamp": datetime.now().isoformat(),
                "metadata": {
                    "online_users": [],
                    "count": 0
                }
            }))
            return

        # Handle diagnostics (LSP messages - ignore or forward)
        if msg_type == "diagnostics":
            # Just log and ignore - these come from the LSP server
            logger.debug(f"📊 Diagnostics received: {message_data.get('uri', 'unknown')}")
            return

        # Unknown message type - log and return error
        logger.warning(f"⚠️ Unknown message type: {msg_type}")
        await websocket.send(json.dumps({
            "type": "error",
            "content": f"Unknown message type: {msg_type}",
            "message": "Supported types: chat, presence"
        }))

    def _extract_message(
        self, data: dict[str, Any], tenant_id: str, user_id: str
    ) -> ChatMessage | None:
        """Convert a flat or nested payload into a ``ChatMessage``."""
        message_data = data.get("message")
        if message_data:
            # Frontend may not send a valid MessageType string inside the nested
            # message, so build the ChatMessage safely with sensible defaults.
            msg_type = MessageType.TEXT
            if "type" in message_data:
                try:
                    msg_type = MessageType(message_data["type"])
                except ValueError:
                    msg_type = MessageType.TEXT
            return ChatMessage(
                message_id=message_data.get("id") or message_data.get("message_id") or _new_id(),
                room_id=message_data.get("room_id") or data.get("room_id", ""),
                tenant_id=message_data.get("tenant_id") or data.get("tenant_id") or tenant_id,
                sender_id=(
                    message_data.get("sender")
                    or message_data.get("user_id")
                    or data.get("user_id")
                    or user_id
                ),
                type=msg_type,
                content=message_data.get("content", ""),
                timestamp=message_data.get("timestamp") or _now_iso(),
                attachments=message_data.get("attachments", []),
                metadata=message_data.get("metadata", {}),
            )

        if data.get("type") != "chat":
            return None

        return ChatMessage(
            message_id=data.get("id") or data.get("message_id") or _new_id(),
            room_id=data.get("room_id", ""),
            tenant_id=data.get("tenant_id") or tenant_id,
            sender_id=data.get("user_id") or data.get("sender_id") or user_id,
            type=MessageType.TEXT,
            content=data.get("content", ""),
            timestamp=data.get("timestamp") or _now_iso(),
            attachments=data.get("attachments", []),
            metadata=data.get("metadata", {}),
        )

    async def broadcast_to_room(
        self, tenant_id: str, room_id: str, message: ChatMessage
    ) -> None:
        """Broadcast a serialized message to every connection in a room."""
        payload = json.dumps(message.to_dict(), default=str)
        clients = self._rooms.get((tenant_id, room_id), set())
        closed: set[Any] = set()
        for ws in clients:
            try:
                await ws.send(payload)
            except websockets.ConnectionClosed:
                closed.add(ws)
        clients -= closed

    async def send_to_user(
        self, tenant_id: str, user_id: str, message: ChatMessage
    ) -> None:
        """Send a direct message to a specific user if they are connected."""
        ws = self._users.get((tenant_id, user_id))
        if ws is None:
            return
        payload = json.dumps(message.to_dict(), default=str)
        try:
            await ws.send(payload)
        except websockets.ConnectionClosed:
            self._users.pop((tenant_id, user_id), None)
