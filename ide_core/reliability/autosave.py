"""Background autosave of dirty documents to a snapshots directory."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ide_core.document_manager import DocumentManager


class AutosaveManager:
    """Periodically persist dirty documents to ``.ide_autosave`` snapshots."""

    def __init__(
        self,
        document_manager: DocumentManager,
        interval: float = 30.0,
        autosave_dir: Path | str | None = None,
    ) -> None:
        self._document_manager = document_manager
        self._interval = interval
        self._autosave_dir = Path(autosave_dir) if autosave_dir else Path(".ide_autosave")
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the background autosave loop."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the background loop and perform one final save."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._save_all()

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self._save_all()

    async def _save_all(self) -> None:
        """Snapshot every currently dirty document."""
        self._autosave_dir.mkdir(parents=True, exist_ok=True)
        for uri in self._document_manager.dirty_uris:
            doc = self._document_manager.get(uri)
            if doc is None:
                continue
            filename = hashlib.sha256(uri.encode("utf-8")).hexdigest() + ".txt"
            target = self._autosave_dir / filename
            target.write_text(doc.get_text(), encoding="utf-8")

    async def save_now(self) -> None:
        """Trigger an immediate autosave cycle."""
        await self._save_all()
