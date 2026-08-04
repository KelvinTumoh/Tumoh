"""Async WebSocket gateway for the unified chat subsystem."""

from __future__ import annotations

import json
from typing import Any, Optional

import websockets

from ide_core.auth.manager import AuthManager
from ide_core.config.settings import IDESettings

from .message_handler import MessageHandler
from .models import ChatContext, ChatMessage, ChatRoom, MessageType, _now_iso
from .presence import PresenceManager
from .room_manager import RoomManager


class ChatWebSocketServer:
    """Serve chat clients over WebSockets with multi-tenant JWT validation."""

    def __init__(
        self,
        settings: Optional[IDESettings] = None,
        auth: Optional[AuthManager] = None,
        message_handler: Optional[MessageHandler] = None,
        presence: Optional[PresenceManager] = None,
        room_manager: Optional[RoomManager] = None,
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

    def _extract_token(self, websocket: Any, path: str) -> Optional[str]:
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
            await self._send(websocket, {"type": "error", "message": "Chat disabled"})
            return

        token = self._extract_token(websocket, path)
        user = self._auth.verify_token(token) if token else None
        if user is None:
            await self._send(websocket, {"type": "error", "message": "Unauthorized"})
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
                websocket, {"type": "error", "message": f"Invalid JSON: {exc}"}
            )
        finally:
            self._users.pop((websocket.tenant_id, websocket.user_id), None)
            self._presence.set_offline(websocket.tenant_id, websocket.user_id)
            for clients in self._rooms.values():
                clients.discard(websocket)

    async def _route_message(self, websocket: Any, data: dict[str, Any]) -> None:
        tenant_id = websocket.tenant_id
        user_id = websocket.user_id
        room_id = data.get("room_id")

        if room_id:
            self._rooms.setdefault((tenant_id, room_id), set()).add(websocket)

        message_data = data.get("message")
        if message_data:
            message = ChatMessage.from_dict(message_data)
            context = ChatContext(
                tenant_id=tenant_id,
                user_id=user_id,
                room_id=room_id,
            )
            replies = await self._handler.process_message(message, context)
            for reply in replies:
                await self.broadcast_to_room(tenant_id, room_id, reply)

        if data.get("type") == "presence" and room_id:
            presence = self._presence.broadcast_presence(tenant_id, room_id)
            await self.broadcast_to_room(tenant_id, room_id, ChatMessage.from_dict(presence))

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
