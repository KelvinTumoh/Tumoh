"""Interactive terminal manager for persistent subshell sessions."""

from __future__ import annotations

import asyncio
import inspect
import shlex
import sys
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ide_core.security import SecurityManager


class TerminalManager:
    """Run a persistent shell, stream output, and keep a recent output buffer."""

    def __init__(
        self,
        shell_command: list[str] | None = None,
        output_callback: Callable[[str], Any] | None = None,
        max_history: int = 1000,
        workspace: Path | str | None = None,
        security_manager: SecurityManager | None = None,
        max_runtime: float | None = None,
        max_output_bytes: int = 1_000_000,
    ) -> None:
        self._shell = shell_command or self._default_shell()
        self._process: asyncio.subprocess.Process | None = None
        self._output_callback = output_callback
        self._output_buffer: deque[str] = deque(maxlen=max_history)
        self._read_tasks: list[asyncio.Task[None]] = []
        self._workspace = Path(workspace).expanduser().resolve() if workspace else Path.cwd()
        self._cwd = str(self._workspace)
        self._security = security_manager
        self._max_runtime = max_runtime
        self._max_output_bytes = max_output_bytes
        self._output_bytes = 0
        self._runtime_task: asyncio.Task[None] | None = None

    @staticmethod
    def _default_shell() -> list[str]:
        if sys.platform == "win32":
            return ["cmd.exe", "/Q"]
        return ["bash", "--norc", "--noprofile"]

    def on_output(self, callback: Callable[[str], Any]) -> None:
        """Set or replace the output broadcast callback."""
        self._output_callback = callback

    async def start(self) -> None:
        """Spawn the shell and begin streaming stdout/stderr."""
        if self._process is not None:
            raise RuntimeError("TerminalManager already started")

        self._process = await asyncio.create_subprocess_exec(
            *self._shell,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._cwd,
        )
        self._read_tasks = [
            asyncio.create_task(self._read_stream(self._process.stdout, "out")),
            asyncio.create_task(self._read_stream(self._process.stderr, "err")),
        ]
        if self._max_runtime:
            self._runtime_task = asyncio.create_task(self._enforce_runtime())

    async def _read_stream(
        self, stream: asyncio.StreamReader, _label: str
    ) -> None:
        """Read output lines and broadcast them."""
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                if self._output_bytes + len(text) > self._max_output_bytes:
                    self._emit("Sandbox error: output quota exceeded.")
                    if self._process is not None:
                        self._process.terminate()
                    break
                self._output_bytes += len(text)
                self._output_buffer.append(text)
                if self._output_callback is not None:
                    result = self._output_callback(text)
                    if inspect.iscoroutine(result) or inspect.iscoroutinefunction(
                        self._output_callback
                    ):
                        asyncio.create_task(result)
        except asyncio.CancelledError:
            pass

    async def write(self, data: str) -> None:
        """Send input to the shell, applying sandbox rules when configured."""
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("Terminal not started")

        if self._security is None:
            self._process.stdin.write(data.encode("utf-8"))
            await self._process.stdin.drain()
            return

        for raw_line in data.splitlines(keepends=False):
            if not raw_line.strip():
                continue
            line = raw_line.rstrip("\r")
            stripped = line.strip()

            if stripped.lower().startswith("cd "):
                target = stripped[3:].strip().strip('"').strip("'")
                new_cwd = self._resolve_cwd(target)
                if new_cwd is None:
                    self._emit(f"Sandbox error: cd to {target!r} is outside workspace.")
                    continue
                self._cwd = str(new_cwd)
                self._process.stdin.write(
                    f"cd {self._format_cd(self._cwd)}\n".encode()
                )
                await self._process.stdin.drain()
                continue

            decision = self._security.check_command(stripped)
            if not decision["allowed"]:
                self._emit(f"Sandbox error: {decision['reason']}")
                continue

            self._process.stdin.write(
                f"cd {self._format_cd(self._cwd)} && {line}\n".encode()
            )
            await self._process.stdin.drain()

    def _resolve_cwd(self, target: str) -> Path | None:
        """Resolve a cd target and ensure it stays inside the workspace."""
        raw = Path(target).expanduser()
        if not raw.is_absolute():
            raw = Path(self._cwd) / raw
        resolved = raw.resolve()
        workspace = self._workspace.resolve()
        return resolved if resolved.is_relative_to(workspace) else None

    def _format_cd(self, path: str) -> str:
        """Quote a directory path safely for the current shell."""
        if sys.platform == "win32":
            return f'"{path}"'
        return shlex.quote(path)

    def _emit(self, text: str) -> None:
        """Append a message to the output buffer and callback."""
        line = text + "\n"
        self._output_buffer.append(line)
        if self._output_callback is not None:
            result = self._output_callback(line)
            if inspect.iscoroutine(result) or inspect.iscoroutinefunction(
                self._output_callback
            ):
                asyncio.create_task(result)

    async def _enforce_runtime(self) -> None:
        """Terminate the shell if it exceeds the configured runtime quota."""
        if self._max_runtime is None:
            return
        await asyncio.sleep(self._max_runtime)
        if self._process is not None:
            self._process.terminate()

    def get_recent_output(self, lines: int = 50) -> str:
        """Return the most recent ``lines`` of output as a single string."""
        return "".join(list(self._output_buffer)[-lines:])

    async def stop(self) -> None:
        """Terminate the shell and cleanup background readers."""
        if self._runtime_task is not None:
            self._runtime_task.cancel()
            try:
                await self._runtime_task
            except asyncio.CancelledError:
                pass

        for task in self._read_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if self._process is not None:
            self._process.terminate()
            try:
                await self._process.wait()
            except ProcessLookupError:
                pass
            self._process = None
