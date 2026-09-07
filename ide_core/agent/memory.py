"""Persistent agent memory for context, decisions, and insights."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AgentMemory:
    """Simple JSON-backed key/value memory for the agent."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path).expanduser() if path else Path(".agent_memory.json")
        self._data: dict = {}
        self.load()

    def load(self) -> None:
        """Load memory from disk."""
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._data = {}
        else:
            self._data = {}

    def save(self) -> None:
        """Persist memory to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def remember(self, key: str, value: Any) -> None:
        """Store a value and persist it."""
        self._data[key] = value
        self.save()

    def recall(self, key: str, default: Any = None) -> Any:
        """Retrieve a stored value."""
        return self._data.get(key, default)

    def all(self) -> dict:
        """Return a shallow copy of the entire memory table."""
        return dict(self._data)
