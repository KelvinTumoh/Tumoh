"""Git version control integration for the IDE engine."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


class GitManager:
    """Async Git status, staging, committing, and diff generation."""

    def __init__(self, repo_path: Path | str) -> None:
        self.repo_path = Path(repo_path).expanduser().resolve()

    async def _run(self, *args: str) -> str:
        """Run a Git command and return stdout; raise on failure."""
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.repo_path),
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed: {stderr.decode('utf-8', errors='replace')}"
            )
        return stdout.decode("utf-8", errors="replace")

    async def is_repo(self) -> bool:
        """Return ``True`` if the path is inside a git repository."""
        try:
            await self._run("rev-parse", "--git-dir")
            return True
        except (RuntimeError, FileNotFoundError):
            return False

    async def status(self) -> List[Dict[str, Any]]:
        """Return a list of status entries from ``git status --porcelain``."""
        text = await self._run("status", "--porcelain", "-u")
        entries = []
        for line in text.splitlines():
            if not line:
                continue
            status = line[:2].strip()
            path = line[3:].strip()
            entries.append({"status": status, "path": path})
        return entries

    async def stage(self, paths: List[str]) -> None:
        """Stage the given paths."""
        if not paths:
            return
        await self._run("add", "--", *paths)

    async def unstage(self, paths: List[str]) -> None:
        """Unstage the given paths."""
        if not paths:
            return
        await self._run("reset", "HEAD", "--", *paths)

    async def commit(self, message: str) -> str:
        """Commit staged changes."""
        return await self._run("commit", "-m", message)

    async def diff(
        self, paths: Optional[List[str]] = None, staged: bool = False
    ) -> str:
        """Return a diff for the given paths (default: unstaged)."""
        cmd = ["diff"]
        if staged:
            cmd = ["diff", "--cached"]
        if paths:
            cmd.extend(["--", *paths])
        return await self._run(*cmd)

    async def diff_file(self, path: str, staged: bool = False) -> str:
        """Return a per-file diff."""
        return await self.diff([path], staged=staged)
