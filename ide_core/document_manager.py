"""Document synchronization manager bridging TextBuffer and LSP."""

from __future__ import annotations

from typing import Dict, Optional

from ide_core.buffer import TextBuffer
from ide_core.diagnostics import DiagnosticManager
from ide_core.lsp.protocol import Position
from ide_core.utils.position import offset_to_position


class Document:
    """A single open document tracked by the editor."""

    def __init__(self, uri: str, language_id: str, content: str) -> None:
        self.uri: str = uri
        self.language_id: str = language_id
        self.buffer: TextBuffer = TextBuffer(content)
        self.version: int = 1

    def get_text(self) -> str:
        """Return the current full text of the document."""
        return self.buffer.get_text()

    def __len__(self) -> int:
        return len(self.buffer)


class DocumentManager:
    """Keeps a collection of open documents in sync with an LSP server."""

    def __init__(self, lsp_client, diagnostic_manager: DiagnosticManager) -> None:
        self._lsp_client = lsp_client
        self._diagnostics = diagnostic_manager
        self._documents: Dict[str, Document] = {}
        self._edit_history: List[dict] = []

        lsp_client.on(
            "textDocument/publishDiagnostics", self._on_publish_diagnostics
        )

    def _on_publish_diagnostics(self, params: Optional[dict]) -> None:
        """Callback for LSP ``textDocument/publishDiagnostics`` notifications."""
        if not params:
            return
        uri = params.get("uri")
        diagnostics = params.get("diagnostics", [])
        if uri is not None:
            self._diagnostics.update(uri, diagnostics)

    def get(self, uri: str) -> Optional[Document]:
        """Return the open ``Document`` for ``uri``, if any."""
        return self._documents.get(uri)

    @property
    def edit_history(self) -> List[dict]:
        """Return a shallow copy of recent edits made through this manager."""
        return list(self._edit_history)

    async def open_document(
        self, uri: str, language_id: str, content: str
    ) -> Document:
        """Open a document, notify the LSP server, and track diagnostics."""
        if uri in self._documents:
            raise ValueError(f"Document already open: {uri}")

        document = Document(uri, language_id, content)
        self._documents[uri] = document
        await self._lsp_client.did_open(uri, language_id, content)
        return document

    async def apply_edit(
        self, uri: str, start_index: int, end_index: int, new_text: str
    ) -> Document:
        """Apply a text replacement and send a ``textDocument/didChange`` update.

        The region ``[start_index, end_index)`` is removed and ``new_text`` is
        inserted at ``start_index`` in the document's ``TextBuffer``.
        """
        document = self._documents.get(uri)
        if document is None:
            raise KeyError(f"Document not open: {uri}")

        old_text = document.get_text()
        if start_index < 0 or end_index > len(document) or start_index > end_index:
            raise IndexError(
                f"Edit range [{start_index}, {end_index}) out of bounds "
                f"for document of length {len(document)}"
            )

        start_pos = offset_to_position(old_text, start_index)
        end_pos = offset_to_position(old_text, end_index)

        document.buffer.delete(start_index, end_index)
        if new_text:
            document.buffer.insert(start_index, new_text)

        document.version += 1

        self._edit_history.append(
            {
                "uri": uri,
                "start_index": start_index,
                "end_index": end_index,
                "new_text": new_text,
                "version": document.version,
            }
        )

        content_change = {
            "range": {
                "start": start_pos.to_dict(),
                "end": end_pos.to_dict(),
            },
            "text": new_text,
        }
        await self._lsp_client.did_change(
            uri, document.version, [content_change]
        )
        return document

    async def close_document(self, uri: str) -> None:
        """Close a document, notify the LSP server, and clean up."""
        if uri not in self._documents:
            raise KeyError(f"Document not open: {uri}")

        await self._lsp_client.did_close(uri)
        del self._documents[uri]
        self._diagnostics.clear(uri)
