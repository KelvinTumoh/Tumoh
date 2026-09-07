"""Static file serving for the bundled frontend."""

from __future__ import annotations

import mimetypes
import sys
from pathlib import Path

from websockets.datastructures import Headers
from websockets.http11 import Request, Response


def _frontend_dir() -> Path:
    """Locate the bundled frontend directory at runtime."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "frontend"
    return Path(__file__).resolve().parent.parent / "frontend"


class StaticFileHandler:
    """Serve the frontend SPA from the bundled or source tree directory."""

    def __init__(self, root: Path | str | None = None) -> None:
        self._root = Path(root).resolve() if root else _frontend_dir()

    def handle(self, request: Request) -> Response | None:
        """Return a ``Response`` for a static file request, or ``None``."""
        if request.method not in ("GET", "HEAD"):
            return None

        requested = request.path
        if requested == "/":
            requested = "/index.html"

        target = self._resolve(requested)
        if target is None:
            return self._not_found()

        try:
            body = target.read_bytes()
        except (OSError, FileNotFoundError):
            return self._not_found()

        content_type, _ = mimetypes.guess_type(str(target))
        headers = Headers()
        if content_type:
            headers["Content-Type"] = content_type

        if request.method == "HEAD":
            body = b""

        return Response(
            status_code=200,
            reason_phrase="OK",
            headers=headers,
            body=body,
        )

    def _resolve(self, path: str) -> Path | None:
        """Resolve ``path`` inside the frontend root, blocking traversal."""
        relative = path.lstrip("/")
        target = (self._root / relative).resolve()
        if target.is_dir():
            target = target / "index.html"
        if target.is_relative_to(self._root):
            return target
        return None

    @staticmethod
    def _not_found() -> Response:
        return Response(
            status_code=404,
            reason_phrase="Not Found",
            headers=Headers(),
            body=b"Not Found",
        )
