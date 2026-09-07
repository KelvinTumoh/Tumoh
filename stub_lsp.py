"""Minimal LSP stub for running ide_core.server without a real language server."""

from __future__ import annotations

import json
import os
import sys


def _encode(msg: dict) -> bytes:
    """Serialize a JSON-RPC 2.0 message with Content-Length headers."""
    payload = json.dumps(msg, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
    return header + payload


def _read_message() -> dict | None:
    """Read a single LSP / JSON-RPC message from stdin."""
    header_lines = []
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line == b"\r\n":
            break
        header_lines.append(line)

    headers = {}
    for raw in header_lines:
        text = raw.decode("ascii").strip()
        if ":" in text:
            key, value = text.split(":", 1)
            headers[key.strip().lower()] = value.strip()

    length = int(headers["content-length"])
    payload = sys.stdin.buffer.read(length)
    if len(payload) < length:
        return None
    return json.loads(payload.decode("utf-8"))


def _handle(msg: dict) -> dict | None:
    """Return the JSON-RPC response for an incoming request, or None for notifications."""
    if "id" not in msg:
        return None

    method = msg.get("method")
    if method == "initialize":
        result = {
            "capabilities": {
                "textDocumentSync": 1,
                "completionProvider": {
                    "resolveProvider": False,
                    "triggerCharacters": ["."],
                },
            }
        }
    elif method == "shutdown":
        result = None
    elif method == "textDocument/completion":
        result = {"items": []}
    else:
        result = None

    return {"jsonrpc": "2.0", "id": msg["id"], "result": result}


def main() -> None:
    """Run the synchronous read/response LSP stub loop."""
    # Redirect stderr to the null device so the LSP client (which leaves stderr
    # in a pipe but never reads it) does not deadlock on any Python warnings.
    sys.stderr = open(os.devnull, "w")
    while True:
        msg = _read_message()
        if msg is None:
            break

        if msg.get("method") == "exit":
            break

        resp = _handle(msg)
        if resp is not None:
            sys.stdout.buffer.write(_encode(resp))
            sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
