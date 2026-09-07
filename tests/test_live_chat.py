"""Live end-to-end tests for the four chat creation modalities."""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import uuid
from pathlib import Path

import pytest
import websockets

pytestmark = pytest.mark.integration

SERVER_URL = os.environ.get("IDE_LIVE_CHAT_URL", "ws://localhost:8765")
ROOM_ID = "live-room"
USER_ID = "live-tester"
TENANT_ID = "default"
RECV_TIMEOUT = 20.0
CONNECT_TIMEOUT = 15.0


def _new_id() -> str:
    return uuid.uuid4().hex


def _chat_payload(content: str, msg_type: str = "text") -> dict:
    return {
        "type": "chat",
        "room_id": ROOM_ID,
        "tenant_id": TENANT_ID,
        "user_id": USER_ID,
        "message": {
            "message_id": _new_id(),
            "room_id": ROOM_ID,
            "tenant_id": TENANT_ID,
            "sender_id": USER_ID,
            "type": msg_type,
            "content": content,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "attachments": [],
            "metadata": {},
        },
    }


async def _wait_for_server(url: str = SERVER_URL, timeout: float = CONNECT_TIMEOUT) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            async with websockets.connect(url):
                return
        except Exception:
            await asyncio.sleep(0.3)
    raise RuntimeError(f"Server not available at {url}")


async def _send_and_receive(content: str, msg_type: str = "text") -> dict:
    await _wait_for_server()
    async with websockets.connect(SERVER_URL) as ws:
        await ws.send(json.dumps(_chat_payload(content, msg_type)))

        echo = json.loads(await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT))
        assert echo.get("sender_id") == USER_ID

        reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT))
        return reply


class _Assertions:
    @staticmethod
    def is_creative_result(reply: dict, expected_domain: str) -> None:
        assert reply.get("type") == "creative_result", f"expected creative_result, got {reply!r}"
        assert reply.get("sender_id") == "assistant"
        assert "Created" in reply.get("content", "")
        assert reply.get("attachments"), "expected at least one attachment"
        attachment = reply["attachments"][0]
        assert attachment.get("type") == expected_domain, f"expected {expected_domain}, got {attachment!r}"
        assert attachment.get("path") and Path(attachment["path"]).exists()
        assert attachment.get("preview")


def test_live_chat_text() -> None:
    async def coro() -> None:
        reply = await _send_and_receive("Hello IDE", "text")
        assert reply.get("type") == "text"
        assert reply.get("sender_id") == "assistant"
        assert "Hello IDE" in reply.get("content", "")

    asyncio.run(coro())


def test_live_chat_image() -> None:
    async def coro() -> None:
        reply = await _send_and_receive("draw an image of a robot", "creative_request")
        _Assertions.is_creative_result(reply, "image")

    asyncio.run(coro())


def test_live_chat_photo() -> None:
    async def coro() -> None:
        reply = await _send_and_receive("take a photo of the team", "creative_request")
        _Assertions.is_creative_result(reply, "image")

    asyncio.run(coro())


def test_live_chat_audio() -> None:
    async def coro() -> None:
        reply = await _send_and_receive("record an audio clip", "creative_request")
        _Assertions.is_creative_result(reply, "sound")

    asyncio.run(coro())


def test_live_chat_music() -> None:
    async def coro() -> None:
        reply = await _send_and_receive("compose a music beat duration:2", "creative_request")
        _Assertions.is_creative_result(reply, "sound")

    asyncio.run(coro())


def test_live_chat_video() -> None:
    async def coro() -> None:
        reply = await _send_and_receive("make an animation promo", "creative_request")
        _Assertions.is_creative_result(reply, "video")

    asyncio.run(coro())
