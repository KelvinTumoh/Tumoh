"""Interactive terminal manager for persistent subshell sessions."""

from __future__ import annotations

import asyncio
import inspect
import sys
from collections import deque
from pathlib import Path
from typing import Any, Callable, Coroutine, Deque, List, Optional


class TerminalManager:
    """Run a persistent shell, stream output, and keep a recent output buffer."""

    def __init__(
        self,
        shell_command: Optional[List[str]] = None,
        output_callback: Optional[Callable[[str], Any]] = None,
        max_history: int = 1000,
    ) -> None:
        self._shell = shell_command or self._default_shell()
        self._process: Optional[asyncio.subprocess.Process] = None
        self._output_callback = output_callback
        self._output_buffer: Deque[str] = deque(maxlen=max_history)
        self._read_tasks: List[asyncio.Task[None]] = []
        self._cwd: str = str(Path.cwd())

    @staticmethod
    def _default_shell() -> List[str]:
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
        """Send input to the shell."""
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("Terminal not started")
        self._process.stdin.write(data.encode("utf-8"))
        await self._process.stdin.drain()

    def get_recent_output(self, lines: int = 50) -> str:
        """Return the most recent ``lines`` of output as a single string."""
        return "".join(list(self._output_buffer)[-lines:])

    async def stop(self) -> None:
        """Terminate the shell and cleanup background readers."""
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
