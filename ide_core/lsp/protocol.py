"""Low-level LSP / JSON-RPC 2.0 message helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Dict

import asyncio


@dataclass(frozen=True)
class Position:
    """LSP 0-based text position."""

    line: int
    character: int

    def to_dict(self) -> Dict[str, int]:
        return {"line": self.line, "character": self.character}

    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> Position:
        return cls(line=data["line"], character=data["character"])


@dataclass(frozen=True)
class Range:
    """Inclusive start / exclusive end range in a document."""

    start: Position
    end: Position

    def to_dict(self) -> Dict[str, Any]:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Range:
        return cls(
            start=Position.from_dict(data["start"]),
            end=Position.from_dict(data["end"]),
        )


@dataclass(frozen=True)
class TextDocumentItem:
    """A text document as it is pushed from client to server."""

    uri: str
    language_id: str
    version: int
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uri": self.uri,
            "languageId": self.language_id,
            "version": self.version,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TextDocumentItem:
        return cls(
            uri=data["uri"],
            language_id=data["languageId"],
            version=data["version"],
            text=data["text"],
        )


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 over LSP (Content-Length header)
# ---------------------------------------------------------------------------


def encode_message(msg: dict) -> bytes:
    """Serialize a JSON-RPC 2.0 message with LSP headers."""
    payload = json.dumps(msg, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
    return header + payload


async def decode_message(reader: asyncio.StreamReader) -> dict:
    """Read a single JSON-RPC 2.0 message from ``reader``.

    The reader is consumed until the double CRLF that terminates the
    headers, then exactly ``Content-Length`` payload bytes are read and
    parsed as JSON.
    """
    header_bytes = await reader.readuntil(b"\r\n\r\n")
    header_text = header_bytes.decode("ascii")
    headers: Dict[str, str] = {}
    for line in header_text.strip().split("\r\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()

    content_length_str = headers.get("content-length")
    if content_length_str is None:
        raise ValueError("Missing Content-Length header in LSP message")

    content_length = int(content_length_str)
    payload = await reader.readexactly(content_length)
    return json.loads(payload.decode("utf-8"))
