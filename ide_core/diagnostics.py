"""In-memory storage for LSP textDocument/publishDiagnostics data."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable


class DiagnosticManager:
    """Store, filter, and retrieve diagnostics indexed by document URI."""

    def __init__(self) -> None:
        self._diagnostics: dict[str, list[dict]] = {}
        self._callbacks: list[Callable[[str, list[dict]], None]] = []

    def on_update(
        self, callback: Callable[[str, list[dict]], None]
    ) -> Callable[[str, list[dict]], None]:
        """Register a callback invoked whenever diagnostics are updated."""
        self._callbacks.append(callback)
        return callback

    def update(self, uri: str, diagnostics: list[dict]) -> None:
        """Replace the diagnostics list for ``uri``."""
        self._diagnostics[uri] = list(diagnostics)
        for callback in self._callbacks:
            if inspect.iscoroutinefunction(callback):
                asyncio.create_task(callback(uri, list(diagnostics)))
            else:
                callback(uri, list(diagnostics))

    def get(self, uri: str) -> list[dict]:
        """Return a shallow copy of the diagnostics for ``uri``."""
        return list(self._diagnostics.get(uri, []))

    def clear(self, uri: str) -> None:
        """Remove all stored diagnostics for ``uri``."""
        self._diagnostics.pop(uri, None)

    def all(self) -> dict[str, list[dict]]:
        """Return a shallow copy of the full diagnostics table."""
        return {uri: list(items) for uri, items in self._diagnostics.items()}

    def filter_by_severity(self, uri: str, severity: int) -> list[dict]:
        """Return diagnostics for ``uri`` matching the given LSP severity."""
        return [d for d in self.get(uri) if d.get("severity") == severity]

    def for_uri(self, uri: str) -> str | None:
        """Convenience helper: is there at least one diagnostic for ``uri``?"""
        return uri if self._diagnostics.get(uri) else None
