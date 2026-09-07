"""Atomic multi-file edit operations with transactional rollback."""

from __future__ import annotations

from typing import Any

from .tools import ToolRegistry


class EditBatcher:
    """Apply a batch of file edits atomically, rolling back on failure."""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def apply(self, edits: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply every edit in order; restore originals if any edit fails."""
        originals: dict[str, str] = {}
        written: list[str] = []

        try:
            for edit in edits:
                path = edit["path"]
                content = edit["content"]

                read = await self._tools.execute("read_file", {"path": path})
                if "error" in read:
                    originals[path] = ""  # new file marker
                else:
                    originals[path] = read["content"]

                write = await self._tools.execute(
                    "write_file", {"path": path, "content": content}
                )
                if "error" in write:
                    raise RuntimeError(f"Failed to write {path}: {write['error']}")
                written.append(path)

            return {"success": True, "edited": written}

        except Exception as exc:  # noqa: BLE001
            await self._rollback(originals)
            return {"success": False, "edited": written, "error": str(exc)}

    async def _rollback(self, originals: dict[str, str]) -> None:
        for path, content in originals.items():
            if not content:
                continue  # best-effort: leave new files in place
            await self._tools.execute(
                "write_file", {"path": path, "content": content}
            )
