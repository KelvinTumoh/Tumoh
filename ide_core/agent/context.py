"""Workspace context assembly for the agent."""

from __future__ import annotations

from typing import Any

from ide_core.diagnostics import DiagnosticManager
from ide_core.document_manager import DocumentManager

from .tools import ToolRegistry


class ContextRetriever:
    """Collect current editor and workspace state for the LLM."""

    def __init__(
        self,
        document_manager: DocumentManager,
        diagnostic_manager: DiagnosticManager,
        tool_registry: ToolRegistry,
    ) -> None:
        self._document_manager = document_manager
        self._diagnostic_manager = diagnostic_manager
        self._tool_registry = tool_registry

    async def retrieve(
        self, query: str | None = None, max_files: int = 5
    ) -> dict[str, Any]:
        """Build a context payload for the LLM.

        If ``query`` is supplied, the retriever also searches the workspace
        and reads the most relevant files.
        """
        open_files: list[dict[str, Any]] = []
        for doc in self._document_manager._documents.values():
            open_files.append(
                {
                    "uri": doc.uri,
                    "language_id": doc.language_id,
                    "version": doc.version,
                    "text": doc.get_text(),
                }
            )

        context: dict[str, Any] = {
            "open_files": open_files,
            "diagnostics": self._diagnostic_manager.all(),
            "recent_edits": self._document_manager.edit_history[-20:],
            "relevant_files": [],
        }

        if query:
            search = await self._tool_registry.execute(
                "search_code", {"query": query}
            )
            matches = search.get("matches", [])[:max_files]
            for match in matches:
                read = await self._tool_registry.execute(
                    "read_file", {"path": match["file"]}
                )
                if "content" in read:
                    context["relevant_files"].append(
                        {
                            "path": match["file"],
                            "line": match.get("line"),
                            "content": read["content"],
                        }
                    )

        return context
