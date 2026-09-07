"""Session persistence: save and restore open documents and dirty state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ide_core.document_manager import DocumentManager


class SessionManager:
    """Persist the editor session to disk and restore it on startup."""

    def __init__(
        self,
        document_manager: DocumentManager,
        path: Path | str | None = None,
    ) -> None:
        self._document_manager = document_manager
        self._path = Path(path) if path else Path(".ide_session.json")

    async def save(self) -> None:
        """Snapshot open documents; dirty documents store their full text."""
        snapshot: list[dict[str, object]] = []
        for uri in self._document_manager.open_uris:
            doc = self._document_manager.get(uri)
            if doc is None:
                continue
            snapshot.append(
                {
                    "uri": uri,
                    "language_id": doc.language_id,
                    "version": doc.version,
                    "text": doc.get_text() if doc.is_dirty else None,
                }
            )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    async def restore(self) -> list[str]:
        """Reopen documents from the saved snapshot."""
        if not self._path.exists():
            return []

        data = json.loads(self._path.read_text(encoding="utf-8"))
        restored: list[str] = []
        for entry in data:
            text = entry.get("text")
            uri = entry["uri"]
            if text is None:
                path = self._document_manager._uri_to_path(uri)
                if path.exists():
                    text = path.read_text(encoding="utf-8")
                else:
                    text = ""
            await self._document_manager.open_or_restore(
                uri, entry["language_id"], text
            )
            restored.append(uri)
        return restored
