"""Async LSP client built on top of the JSON-RPC protocol."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any, Dict, List, Optional

from .protocol import Position, TextDocumentItem, decode_message, encode_message


class LSPClient:
    """A simple async Language Server Protocol client.

    This client spawns a language server as a subprocess, manages the
    JSON-RPC request/response lifecycle, and routes notifications to the
    caller through the :meth:`on` callback registration API.
    """

    def __init__(self, command: List[str]) -> None:
        self._command = command
        self._process: Optional[asyncio.subprocess.Process] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._read_task: Optional[asyncio.Task[None]] = None
        self._request_id = 0
        self._pending: Dict[int, asyncio.Future[dict]] = {}
        self._callbacks: Dict[str, List[Callable[[Optional[dict]], Any]]] = {}

    def on(
        self, method: str, callback: Callable[[Optional[dict]], Any]
    ) -> Callable[[Optional[dict]], Any]:
        """Register a callback for server notifications or requests."""
        self._callbacks.setdefault(method, []).append(callback)
        return callback

    async def start(self) -> None:
        """Spawn the language server and start the background read loop."""
        if self._process is not None:
            raise RuntimeError("LSPClient already started")

        self._process = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader = self._process.stdout
        self._writer = self._process.stdin
        if self._reader is None or self._writer is None:
            raise RuntimeError("Failed to create language server streams")

        self._read_task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        """Cancel the read loop and clean up resources."""
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None

        self._reader = None

    async def _read_loop(self) -> None:
        """Continuously decode server messages and route them."""
        if self._reader is None:
            return

        try:
            while True:
                msg = await decode_message(self._reader)
                await self._route_message(msg)
        except (
            asyncio.IncompleteReadError,
            ConnectionResetError,
            asyncio.CancelledError,
        ):
            pass

    async def _route_message(self, msg: dict) -> None:
        """Distribute a single JSON-RPC message to the right handler."""
        if "method" in msg:
            if "id" in msg:
                # Server-initiated request; return an empty result for now.
                await self._send_response(msg["id"], None)
            else:
                # Notification.
                for callback in self._callbacks.get(msg["method"], []):
                    try:
                        callback(msg.get("params"))
                    except Exception:
                        pass
        elif "id" in msg:
            # Response to one of our requests.
            future = self._pending.pop(msg["id"], None)
            if future is not None and not future.done():
                future.set_result(msg)

    async def _send(self, msg: dict) -> None:
        """Encode and write a single JSON-RPC message."""
        if self._writer is None:
            raise RuntimeError("LSPClient is not started")
        self._writer.write(encode_message(msg))
        await self._writer.drain()

    async def _send_notification(self, method: str, params: Optional[dict] = None) -> None:
        """Send a notification that does not expect a response."""
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        await self._send(msg)

    async def _send_request(self, method: str, params: Optional[dict] = None) -> dict:
        """Send a request and await its JSON-RPC response."""
        request_id = self._next_id()
        msg: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            msg["params"] = params

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict] = loop.create_future()
        self._pending[request_id] = future

        try:
            await self._send(msg)
            return await future
        finally:
            self._pending.pop(request_id, None)

    async def _send_response(self, request_id: int, result: Any = None) -> None:
        """Send a JSON-RPC response for a server-initiated request."""
        await self._send(
            {"jsonrpc": "2.0", "id": request_id, "result": result}
        )

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    # -----------------------------------------------------------------------
    # Public lifecycle / message helpers
    # -----------------------------------------------------------------------

    async def initialize(self, root_uri: str) -> dict:
        """Perform the initialize handshake with the server."""
        params = {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "capabilities": {},
        }
        response = await self._send_request("initialize", params)
        await self._send_notification("initialized", {})
        return response

    async def did_open(self, uri: str, language_id: str, text: str, version: int = 1) -> None:
        """Notify the server that a document has been opened."""
        item = TextDocumentItem(uri, language_id, version, text)
        await self._send_notification(
            "textDocument/didOpen", {"textDocument": item.to_dict()}
        )

    async def did_change(
        self, uri: str, version: int, content_changes: List[dict]
    ) -> None:
        """Notify the server that a document has changed."""
        await self._send_notification(
            "textDocument/didChange",
            {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": content_changes,
            },
        )

    async def did_close(self, uri: str) -> None:
        """Notify the server that a document has been closed."""
        await self._send_notification(
            "textDocument/didClose", {"textDocument": {"uri": uri}}
        )

    async def completion(self, uri: str, position: Position) -> dict:
        """Request completion items for ``uri`` at ``position``."""
        return await self._send_request(
            "textDocument/completion",
            {
                "textDocument": {"uri": uri},
                "position": position.to_dict(),
            },
        )

    async def cancel_request(self, request_id: int) -> None:
        """Send a cancellation notification for a pending request."""
        await self._send_notification("$/cancelRequest", {"id": request_id})

    async def shutdown(self) -> None:
        """Request shutdown, send exit, and terminate the subprocess."""
        try:
            await self._send_request("shutdown")
        except (asyncio.CancelledError, ConnectionResetError):
            pass

        try:
            await self._send_notification("exit")
        except (asyncio.CancelledError, ConnectionResetError):
            pass

        await self.stop()

        if self._process is not None:
            await self._process.wait()
            self._process = None
