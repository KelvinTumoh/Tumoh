"""Workspace scanning, file tree, Git status, and environment detection."""

from __future__ import annotations

import fnmatch
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


class ProjectManager:
    """Scan and describe a workspace directory."""

    ALWAYS_IGNORE = {"__pycache__", "node_modules", ".git", ".venv", "venv"}

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self._gitignore_patterns = self._load_gitignore()

    def _load_gitignore(self) -> List[str]:
        gitignore = self.root / ".gitignore"
        if not gitignore.is_file():
            return []

        patterns = []
        for raw in gitignore.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                patterns.append(line.rstrip("/"))
        return patterns

    def _is_ignored(self, path: Path) -> bool:
        rel = path.relative_to(self.root)
        parts = set(rel.parts)
        if parts & self.ALWAYS_IGNORE:
            return True

        # Match .gitignore patterns against the relative path.
        rel_posix = rel.as_posix()
        for pattern in self._gitignore_patterns:
            if pattern.endswith("/"):
                # Directory-only pattern; match any leading component.
                if any(fnmatch.fnmatch(part, pattern[:-1]) for part in rel.parts):
                    return True
            if fnmatch.fnmatch(rel_posix, pattern) or fnmatch.fnmatch(path.name, pattern):
                return True
        return False

    def tree(self, subpath: Optional[Path | str] = None) -> Dict[str, Any]:
        """Return a nested file tree starting from ``subpath``."""
        target = self.root if subpath is None else self.root / subpath
        if not target.is_dir():
            return {
                "name": target.name,
                "path": target.relative_to(self.root).as_posix() if target != self.root else ".",
                "type": "file",
            }
        return self._scan(target)

    def _scan(self, path: Path) -> Dict[str, Any]:
        rel = path.relative_to(self.root).as_posix() if path != self.root else "."
        node: Dict[str, Any] = {
            "name": path.name if path != self.root else self.root.name,
            "path": rel,
            "type": "directory",
            "children": [],
        }

        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return node

        for entry in entries:
            if self._is_ignored(entry):
                continue
            if entry.is_dir():
                node["children"].append(self._scan(entry))
            else:
                child_rel = entry.relative_to(self.root).as_posix()
                node["children"].append(
                    {
                        "name": entry.name,
                        "path": child_rel,
                        "type": "file",
                    }
                )
        return node

    def git_status(self) -> Dict[str, Any]:
        """Return a brief git status summary."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=self.root,
                timeout=10,
            )
            if result.returncode != 0:
                return {"installed": False, "error": result.stderr}
            changes = [
                {"status": line[:2].strip(), "path": line[3:].strip()}
                for line in result.stdout.splitlines()
                if line
            ]
            return {"installed": True, "changes": changes}
        except FileNotFoundError:
            return {"installed": False, "error": "git not found"}

    def environment(self) -> Dict[str, Any]:
        """Detect likely project tooling from root files."""
        env: Dict[str, Any] = {}
        if (self.root / "pyproject.toml").exists():
            env["python"] = True
        if (self.root / "requirements.txt").exists():
            env["requirements"] = True
        if (self.root / "setup.py").exists():
            env["setuptools"] = True
        if (self.root / "package.json").exists():
            env["javascript"] = True
        if (self.root / "Cargo.toml").exists():
            env["rust"] = True
        if (self.root / ".windsurfrules").exists():
            env["windsurf_rules"] = self.root / ".windsurfrules"
        return env
