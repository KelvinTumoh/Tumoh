"""Unit tests for the WebSocket editor gateway."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
import websockets

from ide_core.diagnostics import DiagnosticManager
from ide_core.document_manager import DocumentManager
from ide_core.lsp.protocol import Position
from ide_core.server import EditorServer


class FakeLSPClient:
    """Stub LSP client for server tests."""

    def __init__(self) -> None:
        self.diagnostics_callback = None
        self.did_open = AsyncMock()
        self.did_change = AsyncMock()
        self.did_close = AsyncMock()
        self.completion = AsyncMock(return_value={"result": [{"label": "print"}]})

    def on(self, method: str, callback) -> None:
        if method == "textDocument/publishDiagnostics":
            self.diagnostics_callback = callback

    def publish(self, params: dict) -> None:
        if self.diagnostics_callback is not None:
            self.diagnostics_callback(params)


def test_server_doc_open_and_edit():
    async def coro():
        client = FakeLSPClient()
        diagnostics = DiagnosticManager()
        documents = DocumentManager(client, diagnostics)
        server = EditorServer(client, documents, diagnostics, port=0)
        await server.start()

        try:
            uri = f"ws://localhost:{server.port}"
            async with websockets.connect(uri) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "type": "doc_open",
                            "uri": "file:///a.py",
                            "language_id": "python",
                            "content": "hello",
                        }
                    )
                )
                opened = json.loads(await ws.recv())
                assert opened["type"] == "doc_opened"

                await ws.send(
                    json.dumps(
                        {
                            "type": "doc_edit",
                            "uri": "file:///a.py",
                            "start_index": 2,
                            "end_index": 4,
                            "new_text": "y",
                        }
                    )
                )
                sync = json.loads(await ws.recv())
                assert sync["type"] == "doc_sync"
                assert sync["text"] == "heyo"
        finally:
            await server.stop()

    asyncio.run(coro())


def test_server_completion():
    async def coro():
        client = FakeLSPClient()
        diagnostics = DiagnosticManager()
        documents = DocumentManager(client, diagnostics)
        server = EditorServer(client, documents, diagnostics, port=0)
        await server.start()

        try:
            uri = f"ws://localhost:{server.port}"
            async with websockets.connect(uri) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "type": "doc_open",
                            "uri": "file:///a.py",
                            "language_id": "python",
                            "content": "hello",
                        }
                    )
                )
                await ws.recv()

                await ws.send(
                    json.dumps(
                        {
                            "type": "completion",
                            "uri": "file:///a.py",
                            "offset": 3,
                            "request_id": 7,
                        }
                    )
                )
                resp = json.loads(await ws.recv())
                assert resp["type"] == "completions"
                assert resp["request_id"] == 7
                assert resp["items"] == [{"label": "print"}]

                client.completion.assert_awaited_once_with(
                    "file:///a.py", Position(0, 3)
                )
        finally:
            await server.stop()

    asyncio.run(coro())


def test_server_broadcasts_diagnostics():
    async def coro():
        client = FakeLSPClient()
        diagnostics = DiagnosticManager()
        documents = DocumentManager(client, diagnostics)
        server = EditorServer(client, documents, diagnostics, port=0)
        await server.start()

        try:
            uri = f"ws://localhost:{server.port}"
            async with websockets.connect(uri) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "type": "doc_open",
                            "uri": "file:///a.py",
                            "language_id": "python",
                            "content": "x",
                        }
                    )
                )
                await ws.recv()  # doc_opened

                diagnostics.update(
                    "file:///a.py", [{"message": "syntax error", "severity": 1}]
                )
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                msg = json.loads(raw)
                assert msg["type"] == "diagnostics"
                assert msg["uri"] == "file:///a.py"
                assert msg["diagnostics"][0]["message"] == "syntax error"
        finally:
            await server.stop()

    asyncio.run(coro())


def test_server_unknown_message_type():
    async def coro():
        client = FakeLSPClient()
        diagnostics = DiagnosticManager()
        documents = DocumentManager(client, diagnostics)
        server = EditorServer(client, documents, diagnostics, port=0)
        await server.start()

        try:
            uri = f"ws://localhost:{server.port}"
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"type": "not_a_real_type"}))
                msg = json.loads(await ws.recv())
                assert msg["type"] == "error"
        finally:
            await server.stop()

    asyncio.run(coro())
