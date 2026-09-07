"""Unit tests for session persistence and autosave."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

from ide_core.diagnostics import DiagnosticManager
from ide_core.document_manager import DocumentManager
from ide_core.reliability import AutosaveManager, SessionManager


class FakeLSPClient:
    def __init__(self):
        self.did_open = AsyncMock()
        self.did_change = AsyncMock()
        self.did_close = AsyncMock()

    def on(self, *_args):
        pass


def test_session_save_and_restore(tmp_path: Path):
    async def coro():
        session_path = tmp_path / "session.json"
        uri = str(tmp_path / "a.py")

        client = FakeLSPClient()
        dm = DocumentManager(client, DiagnosticManager())
        await dm.open_document(uri, "python", "x = 1")
        await dm.apply_edit(uri, 5, 5, "\ny = 2")

        session = SessionManager(dm, session_path)
        await session.save()

        assert session_path.exists()
        assert "x = 1" in session_path.read_text(encoding="utf-8")

        dm2 = DocumentManager(client, DiagnosticManager())
        session2 = SessionManager(dm2, session_path)
        restored = await session2.restore()

        assert uri in restored
        doc = dm2.get(uri)
        assert doc is not None
        assert doc.get_text() == "x = 1\ny = 2"

    asyncio.run(coro())


def test_autosave_creates_snapshots(tmp_path: Path):
    async def coro():
        autosave_dir = tmp_path / "autosave"
        uri = str(tmp_path / "a.py")
        client = FakeLSPClient()
        dm = DocumentManager(client, DiagnosticManager())
        await dm.open_document(uri, "python", "dirty")
        await dm.apply_edit(uri, 5, 5, " data")

        autosave = AutosaveManager(dm, autosave_dir=autosave_dir)
        await autosave.save_now()

        snapshots = list(autosave_dir.glob("*.txt"))
        assert len(snapshots) == 1
        assert snapshots[0].read_text(encoding="utf-8") == "dirty data"

    asyncio.run(coro())
