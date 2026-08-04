"""Unified chat subsystem: rooms, presence, WebSocket gateway, and integration."""

from __future__ import annotations

from .integration import UnifiedChatIntegration
from .message_handler import MessageHandler
from .models import ChatContext, ChatMessage, ChatRoom, MessageType
from .presence import PresenceManager
from .room_manager import RoomManager
from .websocket_server import ChatWebSocketServer

__all__ = [
    "ChatContext",
    "ChatMessage",
    "ChatRoom",
    "ChatWebSocketServer",
    "MessageHandler",
    "MessageType",
    "PresenceManager",
    "RoomManager",
    "UnifiedChatIntegration",
]
