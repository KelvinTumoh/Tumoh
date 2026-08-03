"""Unit tests for Document, DocumentManager, and position helpers."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from ide_core.diagnostics import DiagnosticManager
from ide_core.document_manager import Document, DocumentManager
from ide_core.lsp.protocol import Position
from ide_core.utils.position import offset_to_position, position_to_offset


class FakeLSPClient:
    """Stub LSP client for DocumentManager tests."""

    def __init__(self) -> None:
        self.diagnostics_callback = None
        self.did_open = AsyncMock()
        self.did_change = AsyncMock()
        self.did_close = AsyncMock()

    def on(self, method: str, callback) -> None:
        if method == "textDocument/publishDiagnostics":
            self.diagnostics_callback = callback

    def publish(self, params: dict) -> None:
        if self.diagnostics_callback is not None:
            self.diagnostics_callback(params)


# ---------------------------------------------------------------------------
# Position helpers
# ---------------------------------------------------------------------------


def test_offset_to_position():
    text = "line1\nline2\nline3"
    assert offset_to_position(text, 0) == Position(0, 0)
    assert offset_to_position(text, 5) == Position(0, 5)
    assert offset_to_position(text, 6) == Position(1, 0)
    assert offset_to_position(text, 11) == Position(1, 5)
    assert offset_to_position(text, 12) == Position(2, 0)


def test_position_to_offset():
    text = "line1\nline2\nline3"
    assert position_to_offset(text, Position(0, 0)) == 0
    assert position_to_offset(text, Position(0, 5)) == 5
    assert position_to_offset(text, Position(1, 0)) == 6
    assert position_to_offset(text, Position(2, 3)) == 15


def test_position_roundtrip():
    text = "abc\ndef\nghi"
    for offset in range(len(text) + 1):
        pos = offset_to_position(text, offset)
        assert position_to_offset(text, pos) == offset


# ---------------------------------------------------------------------------
# Document + DocumentManager
# ---------------------------------------------------------------------------


def test_document_wraps_text_buffer():
    doc = Document("file:///a.py", "python", "hello")
    assert doc.get_text() == "hello"
    assert doc.version == 1
    assert len(doc) == 5


def test_open_document_notifies_server():
    async def coro():
        client = FakeLSPClient()
        dm = DocumentManager(client, DiagnosticManager())
        doc = await dm.open_document("file:///a.py", "python", "hello")

        assert doc is dm.get("file:///a.py")
        assert doc.get_text() == "hello"
        assert doc.version == 1
        client.did_open.assert_awaited_once_with("file:///a.py", "python", "hello")

    asyncio.run(coro())


def test_apply_edit_updates_text_and_version():
    async def coro():
        client = FakeLSPClient()
        dm = DocumentManager(client, DiagnosticManager())
        await dm.open_document("file:///a.py", "python", "hello world")

        doc = await dm.apply_edit("file:///a.py", 6, 11, "everyone")
        assert doc.get_text() == "hello everyone"
        assert doc.version == 2

        client.did_change.assert_awaited_once()
        uri, version, changes = client.did_change.call_args.args
        assert uri == "file:///a.py"
        assert version == 2
        assert changes[0]["text"] == "everyone"
        assert changes[0]["range"]["start"] == {"line": 0, "character": 6}
        assert changes[0]["range"]["end"] == {"line": 0, "character": 11}

    asyncio.run(coro())


def test_apply_edit_across_line_boundaries():
    async def coro():
        client = FakeLSPClient()
        dm = DocumentManager(client, DiagnosticManager())
        await dm.open_document("file:///a.py", "python", "line1\nline2\nline3")

        doc = await dm.apply_edit("file:///a.py", 6, 12, "X\n")
        assert doc.get_text() == "line1\nX\nline3"
        assert doc.version == 2

        _, _, changes = client.did_change.call_args.args
        change = changes[0]
        assert change["text"] == "X\n"
        assert change["range"]["start"] == {"line": 1, "character": 0}
        assert change["range"]["end"] == {"line": 2, "character": 0}

    asyncio.run(coro())


def test_apply_edit_out_of_bounds_raises():
    async def coro():
        client = FakeLSPClient()
        dm = DocumentManager(client, DiagnosticManager())
        await dm.open_document("file:///a.py", "python", "hi")

        with pytest.raises(IndexError):
            await dm.apply_edit("file:///a.py", 5, 10, "x")

    asyncio.run(coro())


def test_diagnostics_are_recorded():
    async def coro():
        client = FakeLSPClient()
        diagnostics = DiagnosticManager()
        dm = DocumentManager(client, diagnostics)
        await dm.open_document("file:///a.py", "python", "x")

        client.publish(
            {"uri": "file:///a.py", "diagnostics": [{"message": "syntax error"}]}
        )
        assert diagnostics.get("file:///a.py") == [{"message": "syntax error"}]

    asyncio.run(coro())


def test_close_document_removes_and_clears_diagnostics():
    async def coro():
        client = FakeLSPClient()
        diagnostics = DiagnosticManager()
        dm = DocumentManager(client, diagnostics)
        await dm.open_document("file:///a.py", "python", "x")

        client.publish(
            {"uri": "file:///a.py", "diagnostics": [{"message": "syntax error"}]}
        )
        await dm.close_document("file:///a.py")

        client.did_close.assert_awaited_once_with("file:///a.py")
        assert dm.get("file:///a.py") is None
        assert diagnostics.get("file:///a.py") == []

    asyncio.run(coro())
