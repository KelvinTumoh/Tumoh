"""Dataclasses and enums for the unified chat subsystem."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    """Return a short hex UUID suitable for message and room IDs."""
    return uuid.uuid4().hex


class MessageType(Enum):
    """Supported categories of chat messages and events."""

    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"
    PDF = "pdf"
    CREATIVE_REQUEST = "creative_request"
    CREATIVE_RESULT = "creative_result"
    SYSTEM = "system"
    PRESENCE = "presence"


@dataclass
class ChatMessage:
    """A single chat message or event inside a tenant-scoped room."""

    message_id: str
    room_id: str
    tenant_id: str
    sender_id: str
    type: MessageType
    content: str
    timestamp: str
    attachments: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the message to a JSON-friendly dict."""
        data = asdict(self)
        data["type"] = self.type.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatMessage":
        """Hydrate a message from its serialized dict form."""
        data = dict(data)
        data["type"] = MessageType(data["type"])
        return cls(**data)


@dataclass
class ChatRoom:
    """A tenant-isolated chat room with a participant list."""

    room_id: str
    tenant_id: str
    name: str
    participants: list[str]
    created_at: str
    is_private: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize the room to a JSON-friendly dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatRoom":
        """Hydrate a room from its serialized dict form."""
        return cls(**data)


@dataclass
class ChatContext:
    """Runtime context for a single user in a chat room."""

    tenant_id: str
    user_id: str
    room_id: str
    history: list[ChatMessage] = field(default_factory=list)
