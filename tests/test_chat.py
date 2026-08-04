"""Tests for the unified chat subsystem (Phase 5)."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import websockets

from ide_core.auth.manager import AuthManager, User
from ide_core.chat import (
    ChatContext,
    ChatMessage,
    ChatWebSocketServer,
    MessageHandler,
    MessageType,
    PresenceManager,
    RoomManager,
    UnifiedChatIntegration,
)
from ide_core.chat.models import ChatRoom, _now_iso
from ide_core.config.settings import IDESettings
from ide_core.creative.models import CreativeDomain, CreativeResult
from ide_core.multimodal.models import InputType, MultimodalInput, ProcessedInput


def _chat_settings(tmp_path):
    return IDESettings(
        log_path=str(tmp_path / "ide_engine.log"),
        personality_storage_path=str(tmp_path / "personality"),
        preference_storage_path=str(tmp_path / "preferences"),
        creative_tools_path=str(tmp_path / "creative"),
    )


def _message(
    tenant_id="t1",
    room_id="r1",
    user_id="u1",
    sender_id=None,
    type=MessageType.TEXT,
    content="hello",
    attachments=None,
    metadata=None,
):
    return ChatMessage(
        message_id=uuid.uuid4().hex,
        room_id=room_id,
        tenant_id=tenant_id,
        sender_id=sender_id or user_id,
        type=type,
        content=content,
        timestamp=_now_iso(),
        attachments=attachments or [],
        metadata=metadata or {},
    )


def _context(tenant_id="t1", user_id="u1", room_id="r1"):
    return ChatContext(tenant_id=tenant_id, user_id=user_id, room_id=room_id)


def test_message_type_values():
    assert MessageType.TEXT.value == "text"
    assert MessageType.VOICE.value == "voice"
    assert MessageType.IMAGE.value == "image"
    assert MessageType.PDF.value == "pdf"
    assert MessageType.CREATIVE_REQUEST.value == "creative_request"
    assert MessageType.CREATIVE_RESULT.value == "creative_result"
    assert MessageType.SYSTEM.value == "system"
    assert MessageType.PRESENCE.value == "presence"


def test_chat_message_round_trip():
    msg = _message(content="hi")
    restored = ChatMessage.from_dict(msg.to_dict())
    assert restored == msg


def test_room_manager_create_list_get(tmp_path):
    rm = RoomManager(_chat_settings(tmp_path), storage_root=tmp_path)
    room = rm.create_room("t1", "General", ["u1"])
    assert room.tenant_id == "t1"
    assert room.name == "General"
    assert "u1" in room.participants

    rooms = rm.list_rooms("t1", "u1")
    assert len(rooms) == 1
    assert rooms[0].room_id == room.room_id

    found = rm.get_room("t1", room.room_id)
    assert found is not None
    assert found.name == "General"


def test_room_manager_join_and_leave(tmp_path):
    rm = RoomManager(_chat_settings(tmp_path), storage_root=tmp_path)
    room = rm.create_room("t1", "Team", ["u1"])
    assert rm.join_room("t1", room.room_id, "u2")
    assert "u2" in rm.get_room("t1", room.room_id).participants
    assert rm.leave_room("t1", room.room_id, "u2")
    assert "u2" not in rm.get_room("t1", room.room_id).participants


def test_room_manager_multitenant_isolation(tmp_path):
    rm = RoomManager(_chat_settings(tmp_path), storage_root=tmp_path)
    a = rm.create_room("tenant-a", "A", ["u1"])
    b = rm.create_room("tenant-b", "B", ["u1"])

    a_rooms = rm.list_rooms("tenant-a", "u1")
    b_rooms = rm.list_rooms("tenant-b", "u1")
    assert len(a_rooms) == 1 and a_rooms[0].tenant_id == "tenant-a"
    assert len(b_rooms) == 1 and b_rooms[0].tenant_id == "tenant-b"

    assert rm.get_room("tenant-b", a.room_id) is None
    assert rm.get_room("tenant-a", b.room_id) is None


def test_presence_manager_online_offline(tmp_path):
    rm = RoomManager(_chat_settings(tmp_path), storage_root=tmp_path)
    room = rm.create_room("t1", "Hub", ["u1", "u2"])
    pm = PresenceManager(rm)

    pm.set_online("t1", "u1")
    pm.set_online("t1", "u2")
    online = pm.get_online_users("t1", room.room_id)
    assert set(online) == {"u1", "u2"}

    pm.set_offline("t1", "u2")
    online = pm.get_online_users("t1", room.room_id)
    assert online == ["u1"]


def test_presence_broadcast(tmp_path):
    rm = RoomManager(_chat_settings(tmp_path), storage_root=tmp_path)
    room = rm.create_room("t1", "Hub", ["u1"])
    pm = PresenceManager(rm)
    pm.set_online("t1", "u1")

    event = pm.broadcast_presence("t1", room.room_id)
    assert event["type"] == "presence"
    assert "u1" in event["metadata"]["online_users"]


def test_unified_chat_routes_text(tmp_path):
    settings = _chat_settings(tmp_path)
    settings.chat_enable_friends = False
    integration = UnifiedChatIntegration(settings)
    msg = _message(content="hello")
    ctx = _context()

    result = asyncio.run(integration.route(msg, ctx))
    assert len(result) == 1
    assert result[0].type == MessageType.TEXT
    assert "hello" in result[0].content


def test_unified_chat_routes_voice_image_pdf(tmp_path):
    settings = _chat_settings(tmp_path)
    settings.chat_enable_friends = False
    multimodal = MagicMock()
    multimodal.process_input = AsyncMock(
        return_value=ProcessedInput(
            input_id="x",
            raw_text="extracted payload",
            intent="general",
        )
    )
    integration = UnifiedChatIntegration(settings, multimodal=multimodal)

    for mtype, kind in [
        (MessageType.VOICE, "voice"),
        (MessageType.IMAGE, "image"),
        (MessageType.PDF, "pdf"),
    ]:
        msg = _message(
            type=mtype,
            content=f"[{kind}]",
            attachments=[{"type": kind, "payload": b"fake bytes"}],
        )
        result = asyncio.run(integration.route(msg, _context()))
        assert len(result) == 1
        assert result[0].type == MessageType.TEXT
        assert "extracted payload" in result[0].content
        multimodal.process_input.assert_awaited()
        multimodal.process_input.reset_mock()


def test_unified_chat_creative_request(tmp_path):
    settings = _chat_settings(tmp_path)
    settings.chat_enable_friends = False
    creative = MagicMock()
    creative.execute = AsyncMock(
        return_value=CreativeResult(
            request_id="x",
            success=True,
            domain=CreativeDomain.IMAGE,
            output_path="/tmp/out.svg",
            message="SVG generated",
        )
    )
    integration = UnifiedChatIntegration(settings, creative=creative)
    msg = _message(type=MessageType.CREATIVE_REQUEST, content="draw a logo")

    result = asyncio.run(integration.route(msg, _context()))
    assert len(result) == 1
    assert result[0].type == MessageType.CREATIVE_RESULT
    assert creative.execute.awaited


def test_unified_chat_agent_orchestrator(tmp_path):
    settings = _chat_settings(tmp_path)
    settings.chat_enable_friends = False
    orchestrator = MagicMock()
    orchestrator.run = AsyncMock(return_value=[{"role": "assistant", "content": "Done"}])
    integration = UnifiedChatIntegration(settings, orchestrator=orchestrator)
    msg = _message(content="refactor the main loop")

    result = asyncio.run(integration.route(msg, _context()))
    assert len(result) == 1
    assert result[0].type == MessageType.TEXT
    assert orchestrator.run.awaited


def test_message_handler_persists_and_routes(tmp_path):
    settings = _chat_settings(tmp_path)
    settings.chat_enable_friends = False
    integration = MagicMock()
    reply = _message(type=MessageType.TEXT, content="reply")
    integration.route = AsyncMock(return_value=[reply])

    handler = MessageHandler(settings, integration=integration, storage_root=tmp_path)
    msg = _message(content="hello")
    ctx = _context()

    result = asyncio.run(handler.process_message(msg, ctx))
    assert len(result) == 2
    assert result[1].content == "reply"

    persisted = Path(tmp_path / "t1" / f"messages_r1.json").read_text()
    data = json.loads(persisted)
    assert len(data) == 2
    assert data[0]["content"] == "hello"
    assert data[1]["content"] == "reply"


def test_message_handler_multitenant_message_isolation(tmp_path):
    settings = _chat_settings(tmp_path)
    settings.chat_enable_friends = False
    integration = MagicMock()
    integration.route = AsyncMock(return_value=[])
    handler = MessageHandler(settings, integration=integration, storage_root=tmp_path)

    a = _message(tenant_id="tenant-a", room_id="room-1", content="A")
    b = _message(tenant_id="tenant-b", room_id="room-1", content="B")
    asyncio.run(handler.process_message(a, _context("tenant-a", "u1", "room-1")))
    asyncio.run(handler.process_message(b, _context("tenant-b", "u1", "room-1")))

    a_log = json.loads((tmp_path / "tenant-a" / "messages_room-1.json").read_text())
    b_log = json.loads((tmp_path / "tenant-b" / "messages_room-1.json").read_text())
    assert all(m["tenant_id"] == "tenant-a" for m in a_log)
    assert all(m["tenant_id"] == "tenant-b" for m in b_log)
    assert len(a_log) == 1
    assert len(b_log) == 1


def test_message_handler_feature_disabled(tmp_path):
    settings = _chat_settings(tmp_path)
    settings.enable_chat = False
    handler = MessageHandler(settings, integration=MagicMock(), storage_root=tmp_path)
    msg = _message(content="hello")

    result = asyncio.run(handler.process_message(msg, _context()))
    assert any(r.type == MessageType.SYSTEM for r in result)


def test_websocket_handle_connection(tmp_path):
    settings = _chat_settings(tmp_path)
    settings.chat_enable_friends = False
    auth = AuthManager(settings)
    token = auth.create_token(User(user_id="u1", name="User", tenant_id="t1"))

    message = _message(content="hello").to_dict()
    reply = _message(sender_id="assistant", content="hi there").to_dict()
    handler = MagicMock()
    handler.process_message = AsyncMock(return_value=[ChatMessage.from_dict(message), ChatMessage.from_dict(reply)])

    server = ChatWebSocketServer(settings, auth=auth, message_handler=handler)
    fake_ws = AsyncMock()
    fake_ws.request_headers = {"Authorization": f"Bearer {token}"}
    fake_ws.recv = AsyncMock(side_effect=[
        json.dumps({"room_id": "r1", "message": message}),
        websockets.ConnectionClosed(None, None),
    ])

    asyncio.run(server.handle_connection(fake_ws, "/ws/chat"))

    assert fake_ws.send.called
    assert fake_ws.tenant_id == "t1"
    assert fake_ws.user_id == "u1"
    handler.process_message.assert_awaited_once()


def test_websocket_unauthorized(tmp_path):
    settings = _chat_settings(tmp_path)
    auth = AuthManager(settings)
    server = ChatWebSocketServer(settings, auth=auth)
    fake_ws = AsyncMock()
    fake_ws.request_headers = {}
    fake_ws.recv = AsyncMock(side_effect=websockets.ConnectionClosed(None, None))

    asyncio.run(server.handle_connection(fake_ws, "/ws/chat"))
    assert fake_ws.send.called
    calls = [str(c.args[0]) for c in fake_ws.send.call_args_list]
    assert any("Unauthorized" in c for c in calls)


def test_websocket_broadcast_to_room(tmp_path):
    settings = _chat_settings(tmp_path)
    server = ChatWebSocketServer(settings)
    fake_ws = AsyncMock()
    server._rooms[("t1", "r1")] = {fake_ws}
    msg = _message(content="broadcast")

    asyncio.run(server.broadcast_to_room("t1", "r1", msg))
    assert fake_ws.send.called


def test_websocket_send_to_user(tmp_path):
    settings = _chat_settings(tmp_path)
    server = ChatWebSocketServer(settings)
    fake_ws = AsyncMock()
    server._users[("t1", "u1")] = fake_ws
    msg = _message(content="dm")

    asyncio.run(server.send_to_user("t1", "u1", msg))
    assert fake_ws.send.called


def test_feature_flag_disable_chat(tmp_path):
    settings = _chat_settings(tmp_path)
    settings.enable_chat = False
    server = ChatWebSocketServer(settings)
    fake_ws = AsyncMock()

    asyncio.run(server.handle_connection(fake_ws, "/ws/chat"))
    assert fake_ws.send.called
    assert any("disabled" in str(c.args[0]).lower() for c in fake_ws.send.call_args_list)
