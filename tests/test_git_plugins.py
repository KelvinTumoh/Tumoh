"""Unit tests for the Git subsystem."""

import asyncio
import subprocess
import tempfile
from pathlib import Path

from ide_core.git.manager import GitManager


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path,
        check=True,
        capture_output=True,
    )


def test_git_repo_detection():
    async def coro():
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            _init_git_repo(path)
            gm = GitManager(path)
            assert await gm.is_repo()

    asyncio.run(coro())


def test_git_status_stage_commit_and_diff():
    async def coro():
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            _init_git_repo(path)

            # Create an initial file and commit so we have a HEAD.
            (path / "README.md").write_text("# Hello")
            subprocess.run(
                ["git", "add", "README.md"], cwd=path, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=path,
                check=True,
                capture_output=True,
            )

            gm = GitManager(path)
            status_before = await gm.status()
            assert not any(s["path"] == "main.py" for s in status_before)

            (path / "main.py").write_text("print(1)")
            status_after = await gm.status()
            assert any(s["path"] == "main.py" for s in status_after)

            await gm.stage(["main.py"])
            status_staged = await gm.status()
            staged = next((s for s in status_staged if s["path"] == "main.py"), None)
            assert staged and staged["status"] == "A"

            diff = await gm.diff_file("main.py", staged=True)
            assert "print(1)" in diff

            await gm.commit("add main")
            status_clean = await gm.status()
            assert not any(s["path"] == "main.py" for s in status_clean)

    asyncio.run(coro())
