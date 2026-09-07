"""Agent tool registry: file, search, command, and diagnostic tools."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from ide_core.diagnostics import DiagnosticManager
from ide_core.document_manager import DocumentManager
from ide_core.security import SecurityManager


class ToolRegistry:
    """Callable tools the agent can invoke to inspect and modify a workspace."""

    def __init__(
        self,
        workspace: Path | str,
        document_manager: DocumentManager,
        diagnostic_manager: DiagnosticManager,
        security_manager: SecurityManager | None = None,
    ) -> None:
        self._workspace = Path(workspace).expanduser().resolve()
        self._document_manager = document_manager
        self._diagnostic_manager = diagnostic_manager
        self._security = security_manager or SecurityManager()

    # -----------------------------------------------------------------------
    # Schema export for LLM tool binding
    # -----------------------------------------------------------------------

    def get_schemas(self) -> list[dict]:
        """Return OpenAI-style function schemas for every available tool."""
        return [
            _schema(
                "read_file",
                "Read the UTF-8 text of a file within the workspace.",
                {"path": {"type": "string", "description": "Relative or absolute file path"}},
                ["path"],
            ),
            _schema(
                "write_file",
                "Write UTF-8 text to a file, creating parent directories if needed.",
                {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                ["path", "content"],
            ),
            _schema(
                "search_code",
                "Search for a string in workspace source files.",
                {
                    "query": {"type": "string"},
                    "path": {
                        "type": "string",
                        "description": "Subdirectory to search, defaults to workspace root",
                    },
                },
                ["query"],
            ),
            _schema(
                "run_command",
                "Run a shell command and return exit code, stdout, and stderr.",
                {
                    "command": {"type": "string"},
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory for the command",
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": "Whether the user has confirmed a risky command",
                    },
                },
                ["command"],
            ),
            _schema(
                "get_diagnostics",
                "Fetch the current LSP diagnostics for an open document URI.",
                {"uri": {"type": "string"}},
                ["uri"],
            ),
        ]

    # -----------------------------------------------------------------------
    # Execution
    # -----------------------------------------------------------------------

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict:
        """Run the named tool with the provided JSON arguments."""
        try:
            handler = getattr(self, f"_{name}")
        except AttributeError:
            return {"error": f"Unknown tool {name!r}"}

        try:
            return await handler(**arguments)
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    # -----------------------------------------------------------------------
    # Tool implementations
    # -----------------------------------------------------------------------

    async def _read_file(self, path: str) -> dict:
        target = self._resolve(path)
        content = await asyncio.to_thread(target.read_text, encoding="utf-8")
        return {"path": str(target), "content": content}

    async def _write_file(self, path: str, content: str) -> dict:
        target = self._resolve(path)
        if not target.parent.exists():
            await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_text, content, encoding="utf-8")
        return {"path": str(target), "bytes_written": len(content.encode("utf-8"))}

    async def _search_code(self, query: str, path: str = ".") -> dict:
        root = self._resolve(path)
        if not root.is_dir():
            return {"error": f"{path!r} is not a directory"}

        if shutil.which("rg") is not None:
            return await self._search_with_ripgrep(query, root)
        return await self._search_with_python(query, root)

    async def _search_with_ripgrep(self, query: str, root: Path) -> dict:
        proc = await asyncio.create_subprocess_exec(
            "rg",
            "-n",
            "--max-columns",
            "200",
            "--",
            query,
            str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode not in (0, 1):  # rg returns 1 when no matches
            return {"error": stderr.decode("utf-8", errors="replace")}

        matches = []
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            if ":" in line:
                file, _, rest = line.partition(":")
                line_no, _, text = rest.partition(":")
                matches.append({"file": file, "line": int(line_no) if line_no.isdigit() else 0, "text": text})
        return {"matches": matches, "count": len(matches)}

    async def _search_with_python(self, query: str, root: Path) -> dict:
        matches = []

        def _walk():
            for file in root.rglob("*"):
                if not file.is_file() or file.is_dir():
                    continue
                if file.suffix not in (".py", ".txt", ".md", ".json", ".yaml", ".yml"):
                    continue
                try:
                    text = file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for i, line in enumerate(text.splitlines(), start=1):
                    if query in line:
                        matches.append({"file": str(file), "line": i, "text": line[:200]})

        await asyncio.to_thread(_walk)
        return {"matches": matches, "count": len(matches)}

    async def _run_command(
        self, command: str, cwd: str | None = None, confirmed: bool = False
    ) -> dict:
        workdir = self._workspace if cwd is None else self._resolve(cwd)
        decision = self._security.check_command(command, confirmed=confirmed)
        if not decision["allowed"]:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": decision["reason"],
            }

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workdir),
        )
        stdout, stderr = await proc.communicate()
        return {
            "exit_code": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }

    async def _get_diagnostics(self, uri: str) -> dict:
        return {"uri": uri, "diagnostics": self._diagnostic_manager.get(uri)}

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _resolve(self, path: str) -> Path:
        target = Path(path).expanduser()
        if not target.is_absolute():
            target = self._workspace / target
        target = target.resolve()
        if not target.is_relative_to(self._workspace):
            raise ValueError(f"Path {path!r} is outside the workspace")
        return target


def _schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }
