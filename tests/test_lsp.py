"""Unit tests for the LSP protocol and client."""

import asyncio
import json
from typing import Any, List

import pytest

from ide_core.lsp.client import LSPClient
from ide_core.lsp.protocol import (
    Position,
    Range,
    TextDocumentItem,
    decode_message,
    encode_message,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_messages(buffer: bytes) -> List[dict]:
    """Parse all JSON-RPC messages from a byte buffer."""
    messages: List[dict] = []
    while b"\r\n\r\n" in buffer:
        header, _, rest = buffer.partition(b"\r\n\r\n")
        if b"Content-Length:" not in header:
            break
        length = int(header.split(b":", 1)[1].strip())
        payload = rest[:length]
        buffer = rest[length:]
        messages.append(json.loads(payload.decode("utf-8")))
    return messages


class FakeWriter:
    """Mock StreamWriter that simply records every byte written."""

    def __init__(self) -> None:
        self.buffer = b""

    def write(self, data: bytes) -> None:
        self.buffer += data

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


class FakeProcess:
    """Minimal fake asyncio.subprocess.Process for unit tests."""

    def __init__(self, stdout: asyncio.StreamReader, stdin: FakeWriter) -> None:
        self.stdout = stdout
        self.stdin = stdin
        self.waited = False

    async def wait(self) -> int:
        self.waited = True
        return 0


# ---------------------------------------------------------------------------
# Protocol tests
# ---------------------------------------------------------------------------


def test_encode_message():
    msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    raw = encode_message(msg)
    header, sep, payload = raw.partition(b"\r\n\r\n")
    assert header.startswith(b"Content-Length:")
    assert payload == json.dumps(msg, separators=(",", ":")).encode("utf-8")


def test_decode_message():
    async def coro():
        msg = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        raw = encode_message(msg)
        reader = asyncio.StreamReader()
        reader.feed_data(raw)
        reader.feed_eof()
        decoded = await decode_message(reader)
        assert decoded == msg

    asyncio.run(coro())


def test_decode_message_requires_content_length():
    async def coro():
        reader = asyncio.StreamReader()
        reader.feed_data(b"Content-Type: application/vscode-jsonrpc\r\n\r\n{}")
        reader.feed_eof()
        with pytest.raises(ValueError):
            await decode_message(reader)

    asyncio.run(coro())


def test_position_range_item_dataclasses():
    pos = Position(line=2, character=5)
    assert pos.to_dict() == {"line": 2, "character": 5}
    assert Position.from_dict(pos.to_dict()) == pos

    rng = Range(start=pos, end=Position(line=3, character=0))
    assert rng.to_dict()["start"] == pos.to_dict()

    doc = TextDocumentItem(
        uri="file:///c:/project/main.py",
        language_id="python",
        version=1,
        text="hello",
    )
    assert doc.to_dict()["languageId"] == "python"
    assert TextDocumentItem.from_dict(doc.to_dict()) == doc


# ---------------------------------------------------------------------------
# Client tests
# ---------------------------------------------------------------------------


def test_client_initialize_handshake(monkeypatch):
    async def coro():
        stdout = asyncio.StreamReader()
        stdin = FakeWriter()
        fake_process = FakeProcess(stdout, stdin)

        async def fake_create(*_args, **_kwargs):
            return fake_process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

        client = LSPClient(["mock-server"])
        await client.start()

        async def feed_response():
            await asyncio.sleep(0)
            stdout.feed_data(
                encode_message(
                    {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}}
                )
            )

        result = (await asyncio.gather(client.initialize("file:///c:/project"), feed_response()))[0]
        assert result["result"] == {"capabilities": {}}

        sent = parse_messages(stdin.buffer)
        assert sent[0]["method"] == "initialize"
        assert sent[0]["params"]["rootUri"] == "file:///c:/project"
        assert sent[1]["method"] == "initialized"

    asyncio.run(coro())


def test_client_did_open(monkeypatch):
    async def coro():
        stdout = asyncio.StreamReader()
        stdin = FakeWriter()
        fake_process = FakeProcess(stdout, stdin)

        async def fake_create(*_args, **_kwargs):
            return fake_process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

        client = LSPClient(["mock-server"])
        await client.start()
        await client.did_open("file:///c:/project/main.py", "python", "print(1)")

        sent = parse_messages(stdin.buffer)
        assert sent[0]["method"] == "textDocument/didOpen"
        assert sent[0]["params"]["textDocument"]["uri"] == "file:///c:/project/main.py"

    asyncio.run(coro())


def test_client_did_change(monkeypatch):
    async def coro():
        stdout = asyncio.StreamReader()
        stdin = FakeWriter()
        fake_process = FakeProcess(stdout, stdin)

        async def fake_create(*_args, **_kwargs):
            return fake_process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

        client = LSPClient(["mock-server"])
        await client.start()
        await client.did_change(
            "file:///c:/project/main.py",
            version=2,
            content_changes=[{"range": {}, "text": "hi"}],
        )

        sent = parse_messages(stdin.buffer)
        assert sent[0]["method"] == "textDocument/didChange"
        assert sent[0]["params"]["contentChanges"][0]["text"] == "hi"

    asyncio.run(coro())


def test_client_cancel_request(monkeypatch):
    async def coro():
        stdout = asyncio.StreamReader()
        stdin = FakeWriter()
        fake_process = FakeProcess(stdout, stdin)

        async def fake_create(*_args, **_kwargs):
            return fake_process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

        client = LSPClient(["mock-server"])
        await client.start()
        await client.cancel_request(42)

        sent = parse_messages(stdin.buffer)
        assert sent[0]["method"] == "$/cancelRequest"
        assert sent[0]["params"]["id"] == 42

    asyncio.run(coro())


def test_client_routes_notification(monkeypatch):
    async def coro():
        stdout = asyncio.StreamReader()
        stdin = FakeWriter()
        fake_process = FakeProcess(stdout, stdin)

        async def fake_create(*_args, **_kwargs):
            return fake_process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

        client = LSPClient(["mock-server"])
        received: List[Any] = []
        client.on("textDocument/publishDiagnostics", received.append)
        await client.start()

        stdout.feed_data(
            encode_message(
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/publishDiagnostics",
                    "params": {"uri": "file:///a.py"},
                }
            )
        )
        await asyncio.sleep(0)

        assert len(received) == 1
        assert received[0]["uri"] == "file:///a.py"

    asyncio.run(coro())


def test_client_handles_server_initiated_request(monkeypatch):
    async def coro():
        stdout = asyncio.StreamReader()
        stdin = FakeWriter()
        fake_process = FakeProcess(stdout, stdin)

        async def fake_create(*_args, **_kwargs):
            return fake_process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

        client = LSPClient(["mock-server"])
        await client.start()

        stdout.feed_data(
            encode_message(
                {
                    "jsonrpc": "2.0",
                    "id": 99,
                    "method": "workspace/applyEdit",
                    "params": {"edit": {}},
                }
            )
        )
        await asyncio.sleep(0)

        sent = parse_messages(stdin.buffer)
        assert any(m.get("id") == 99 and "result" in m for m in sent)

    asyncio.run(coro())


def test_client_shutdown(monkeypatch):
    async def coro():
        stdout = asyncio.StreamReader()
        stdin = FakeWriter()
        fake_process = FakeProcess(stdout, stdin)

        async def fake_create(*_args, **_kwargs):
            return fake_process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

        client = LSPClient(["mock-server"])
        await client.start()

        async def feed_response():
            await asyncio.sleep(0)
            stdout.feed_data(
                encode_message({"jsonrpc": "2.0", "id": 1, "result": None})
            )

        await asyncio.gather(client.shutdown(), feed_response())

        sent = parse_messages(stdin.buffer)
        assert sent[0]["method"] == "shutdown"
        assert sent[1]["method"] == "exit"
        assert fake_process.waited

    asyncio.run(coro())
