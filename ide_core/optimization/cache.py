"""Multi-tier cache for embeddings and parsed code contexts."""

from __future__ import annotations

import hashlib
import pickle
import time
from pathlib import Path
from typing import Any


class SmartCache:
    """In-memory cache with a disk fallback for large or infrequently used values."""

    def __init__(
        self,
        disk_path: Path | str | None = None,
        default_ttl: float = 3600.0,
    ) -> None:
        self._memory: dict[str, Any] = {}
        self._disk = Path(disk_path).expanduser() if disk_path else None
        self._default_ttl = default_ttl

    def _key(self, raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _disk_path(self, key: str) -> Path | None:
        if self._disk is None:
            return None
        return self._disk / f"{key}.pkl"

    def get(self, key: str) -> Any | None:
        """Return the cached value if present and not expired."""
        internal = self._key(key)
        now = time.time()

        if internal in self._memory:
            value, expiry = self._memory[internal]
            if expiry is None or expiry > now:
                return value
            del self._memory[internal]

        path = self._disk_path(internal)
        if path and path.exists():
            try:
                with open(path, "rb") as fh:
                    value, expiry = pickle.load(fh)
                if expiry is None or expiry > now:
                    self._memory[internal] = (value, expiry)
                    return value
                path.unlink(missing_ok=True)
            except (OSError, pickle.PickleError):
                pass

        return None

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Store a value in the in-memory and disk tiers."""
        internal = self._key(key)
        expiry = (
            time.time() + (ttl if ttl is not None else self._default_ttl)
            if (ttl is not None and ttl >= 0)
            else None
        )
        self._memory[internal] = (value, expiry)

        path = self._disk_path(internal)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as fh:
                pickle.dump((value, expiry), fh)

    def clear(self) -> None:
        """Evict all in-memory entries and remove disk cache files."""
        self._memory.clear()
        if self._disk and self._disk.exists():
            for child in self._disk.glob("*.pkl"):
                child.unlink(missing_ok=True)
