"""WebSocket gateway that exposes the editor engine to the Monaco frontend."""

from __future__ import annotations

import asyncio
import json
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import websockets
from websockets.asyncio.server import Server, ServerConnection, serve

from ide_core.config.settings import IDESettings
from ide_core.diagnostics import DiagnosticManager
from ide_core.document_manager import DocumentManager
from ide_core.git.manager import GitManager
from ide_core.lsp.client import LSPClient
from ide_core.project.manager import ProjectManager
from ide_core.tenant.manager import TenantManager
from ide_core.tenant.middleware import TenantMiddleware
from ide_core.terminal import TerminalManager
from ide_core.utils.position import offset_to_position


class EditorServer:
    """WebSocket server bridging ``DocumentManager`` and Monaco UI clients."""

    def __init__(
        self,
        lsp_client: LSPClient,
        document_manager: DocumentManager,
        diagnostic_manager: DiagnosticManager,
        terminal_manager: Optional[TerminalManager] = None,
        project_manager: Optional[ProjectManager] = None,
        git_manager: Optional[GitManager] = None,
        host: str = "localhost",
        port: int = 8765,
        settings: Optional[IDESettings] = None,
        tenant_manager: Optional[TenantManager] = None,
    ) -> None:
        self._lsp_client = lsp_client
        self._document_manager = document_manager
        self._diagnostic_manager = diagnostic_manager
        self._terminal = terminal_manager
        self._project = project_manager
        self._git = git_manager
        self.host = host
        self.port = port
        self._settings = settings or IDESettings()
        self._tenant_manager = tenant_manager or TenantManager(self._settings)
        self._middleware = TenantMiddleware(
            self._handle, self._tenant_manager, self._settings
        )
        self._server: Optional[Server] = None
        self._clients: Set[ServerConnection] = set()

        diagnostic_manager.on_update(self._on_diagnostics)
        if self._terminal is not None:
            self._terminal.on_output(self._on_pty_output)

    async def _on_diagnostics(self, uri: str, diagnostics: List[dict]) -> None:
        """Broadcast diagnostics to every connected UI client."""
        await self._broadcast(
            {"type": "diagnostics", "uri": uri, "diagnostics": diagnostics}
        )

    async def _on_pty_output(self, data: str) -> None:
        """Broadcast shell output to every connected UI client."""
        await self._broadcast({"type": "pty_output", "data": data})

    async def _broadcast(self, msg: Dict[str, Any]) -> None:
        """Send a JSON message to all connected clients, pruning closed ones."""
        if not self._clients:
            return

        payload = json.dumps(msg)
        closed: Set[ServerConnection] = set()
        for ws in self._clients:
            try:
                await ws.send(payload)
            except websockets.ConnectionClosed:
                closed.add(ws)

        self._clients -= closed

    async def _handle(self, ws: ServerConnection) -> None:
        """Serve a single WebSocket client."""
        self._clients.add(ws)
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    await self._route(ws, msg)
                except json.JSONDecodeError as exc:
                    await ws.send(
                        json.dumps(
                            {"type": "error", "message": f"Invalid JSON: {exc}"}
                        )
                    )
        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)

    def _tenant_uri(self, uri: str, tenant_id: Optional[str]) -> str:
        """Return a tenant-scoped document URI."""
        if tenant_id is None:
            return uri
        return f"tenant://{tenant_id}/{uri}"

    def _tenant_path(self, path: str, tenant_id: Optional[str]) -> str:
        """Return a path resolved inside the tenant's isolated workspace."""
        if tenant_id is None:
            return path
        workspace = self._tenant_manager.workspace_for(tenant_id)
        return str(workspace / path.lstrip("/"))

    async def _route(self, ws: ServerConnection, msg: Dict[str, Any]) -> None:
        """Dispatch an inbound WebSocket message to the correct handler."""
        msg_type = msg.get("type")
        tenant_id = getattr(ws, "tenant_id", None)

        if msg_type == "doc_open":
            internal_uri = self._tenant_uri(msg["uri"], tenant_id)
            await self._document_manager.open_document(
                internal_uri, msg["language_id"], msg["content"]
            )
            await ws.send(json.dumps({"type": "doc_opened", "uri": msg["uri"]}))

        elif msg_type == "doc_edit":
            internal_uri = self._tenant_uri(msg["uri"], tenant_id)
            doc = await self._document_manager.apply_edit(
                internal_uri,
                msg["start_index"],
                msg["end_index"],
                msg["new_text"],
            )
            await ws.send(
                json.dumps(
                    {
                        "type": "doc_sync",
                        "uri": msg["uri"],
                        "version": doc.version,
                        "text": doc.get_text(),
                    }
                )
            )

        elif msg_type == "completion":
            uri = msg["uri"]
            internal_uri = self._tenant_uri(uri, tenant_id)
            offset = msg["offset"]
            request_id = msg.get("request_id")

            doc = self._document_manager.get(internal_uri)
            if doc is None:
                await ws.send(
                    json.dumps(
                        {
                            "type": "completions",
                            "request_id": request_id,
                            "items": [],
                        }
                    )
                )
                return

            position = offset_to_position(doc.get_text(), offset)
            response = await self._lsp_client.completion(internal_uri, position)
            items = self._unwrap_completion_result(response)

            await ws.send(
                json.dumps(
                    {"type": "completions", "request_id": request_id, "items": items}
                )
            )

        elif msg_type == "pty_input":
            if self._terminal is None:
                await ws.send(
                    json.dumps({"type": "error", "message": "No terminal configured"})
                )
                return
            await self._terminal.write(msg["data"])
            await ws.send(json.dumps({"type": "pty_ack"}))

        elif msg_type == "get_tree":
            if self._project is None:
                await ws.send(
                    json.dumps({"type": "error", "message": "No project configured"})
                )
                return
            path = self._tenant_path(msg.get("path", ""), tenant_id)
            tree = self._project.tree(path)
            await ws.send(json.dumps({"type": "tree", "tree": tree}))

        elif msg_type == "get_project":
            if self._project is None:
                await ws.send(
                    json.dumps({"type": "error", "message": "No project configured"})
                )
                return
            info = {
                "environment": self._project.environment(),
                "git": self._project.git_status(),
            }
            await ws.send(json.dumps({"type": "project_info", **info}))

        elif msg_type == "git_status":
            if self._git is None:
                await ws.send(
                    json.dumps({"type": "error", "message": "No git manager configured"})
                )
                return
            status = await self._git.status()
            await ws.send(json.dumps({"type": "git_status", "status": status}))

        elif msg_type == "git_diff":
            if self._git is None:
                await ws.send(
                    json.dumps({"type": "error", "message": "No git manager configured"})
                )
                return
            path = self._tenant_path(msg.get("path", ""), tenant_id)
            diff = await self._git.diff_file(path)
            original = await self._git.diff_file(path, staged=False)
            modified = diff  # simplified: display the same diff as modified text
            await ws.send(
                json.dumps({
                    "type": "git_diff",
                    "path": msg.get("path", ""),
                    "original": original,
                    "modified": modified,
                })
            )

        else:
            await ws.send(
                json.dumps({"type": "error", "message": f"Unknown type {msg_type!r}"})
            )

    @staticmethod
    def _unwrap_completion_result(response: dict) -> List[dict]:
        """Normalize an LSP ``textDocument/completion`` response."""
        result = response.get("result")
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("items", [])
        return []

    async def start(self) -> Server:
        """Start the WebSocket server and return the underlying ``Server``."""
        if self._terminal is not None:
            await self._terminal.start()
        self._server = await serve(
            self._middleware,
            self.host,
            self.port,
            process_request=self._middleware.process_request,
        )
        if self.port == 0:
            self.port = self._server.sockets[0].getsockname()[1]
        return self._server

    async def stop(self) -> None:
        """Shut down the WebSocket server."""
        if self._terminal is not None:
            await self._terminal.stop()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None


async def _serve() -> None:
    """Start the production IDE WebSocket gateway from CLI defaults."""
    settings = IDESettings()
    lsp = LSPClient(shlex.split(settings.lsp_python_command))
    await lsp.start()
    try:
        diagnostics = DiagnosticManager()
        documents = DocumentManager(lsp, diagnostics)
        terminal = TerminalManager()
        project = ProjectManager(Path.cwd())
        git = GitManager(Path.cwd())
        server = EditorServer(
            lsp_client=lsp,
            document_manager=documents,
            diagnostic_manager=diagnostics,
            terminal_manager=terminal,
            project_manager=project,
            git_manager=git,
            host=settings.ide_host,
            port=settings.ide_port,
            settings=settings,
        )
        await lsp.initialize(Path.cwd().as_uri())
        await server.start()
        print(f"IDE server listening on ws://{server.host}:{server.port}")
        try:
            await asyncio.Future()
        finally:
            await server.stop()
    finally:
        await lsp.stop()


if __name__ == "__main__":
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        print("Shutting down.")
