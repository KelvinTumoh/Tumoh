"""In-memory storage for LSP textDocument/publishDiagnostics data."""

from __future__ import annotations

import asyncio
import inspect
from typing import Callable, Dict, List, Optional


class DiagnosticManager:
    """Store, filter, and retrieve diagnostics indexed by document URI."""

    def __init__(self) -> None:
        self._diagnostics: Dict[str, List[dict]] = {}
        self._callbacks: List[Callable[[str, List[dict]], None]] = []

    def on_update(
        self, callback: Callable[[str, List[dict]], None]
    ) -> Callable[[str, List[dict]], None]:
        """Register a callback invoked whenever diagnostics are updated."""
        self._callbacks.append(callback)
        return callback

    def update(self, uri: str, diagnostics: List[dict]) -> None:
        """Replace the diagnostics list for ``uri``."""
        self._diagnostics[uri] = list(diagnostics)
        for callback in self._callbacks:
            if inspect.iscoroutinefunction(callback):
                asyncio.create_task(callback(uri, list(diagnostics)))
            else:
                callback(uri, list(diagnostics))

    def get(self, uri: str) -> List[dict]:
        """Return a shallow copy of the diagnostics for ``uri``."""
        return list(self._diagnostics.get(uri, []))

    def clear(self, uri: str) -> None:
        """Remove all stored diagnostics for ``uri``."""
        self._diagnostics.pop(uri, None)

    def all(self) -> Dict[str, List[dict]]:
        """Return a shallow copy of the full diagnostics table."""
        return {uri: list(items) for uri, items in self._diagnostics.items()}

    def filter_by_severity(self, uri: str, severity: int) -> List[dict]:
        """Return diagnostics for ``uri`` matching the given LSP severity."""
        return [d for d in self.get(uri) if d.get("severity") == severity]

    def for_uri(self, uri: str) -> Optional[str]:
        """Convenience helper: is there at least one diagnostic for ``uri``?"""
        return uri if uri in self._diagnostics and self._diagnostics[uri] else None
