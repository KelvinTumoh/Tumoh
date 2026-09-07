"""Automated release script for the IDE Core project.

Usage:
    python scripts/release.py
    python scripts/release.py --version v1.2.3
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT_FILE = ROOT / "ide_core" / "__init__.py"
PYPROJECT_FILE = ROOT / "pyproject.toml"


def _run_command(command: list[str], *, check: bool = True) -> int:
    """Run a subprocess command from the project root."""
    result = subprocess.run(command, cwd=str(ROOT), check=False)
    if check and result.returncode != 0:
        raise SystemExit(f"Command failed: {' '.join(command)}")
    return result.returncode


def _run_pytest() -> None:
    """Run the full test suite and abort on failure."""
    print("Running pytest...")
    _run_command([sys.executable, "-m", "pytest"])
    print("All tests passed.")


def _current_version() -> str | None:
    """Read the current package version from ide_core/__init__.py."""
    if not INIT_FILE.exists():
        return None
    match = re.search(r'__version__\s*=\s*"([^"]+)"', INIT_FILE.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def _prompt_version() -> str:
    """Prompt the user for a semantic version."""
    current = _current_version() or "0.0.0"
    raw = input(f"Current version is {current}. Enter new version (e.g., v1.0.0): ")
    raw = raw.strip()
    if not raw:
        raise SystemExit("A version is required.")
    if not re.match(r"^v?\d+\.\d+\.\d+$", raw):
        raise SystemExit("Version must follow semantic versioning (e.g., v1.0.0).")
    return raw.lstrip("v")


def _update_init_file(version: str) -> None:
    """Bump the version in ide_core/__init__.py."""
    text = INIT_FILE.read_text(encoding="utf-8")
    if "__version__" in text:
        text = re.sub(
            r'__version__\s*=\s*"[^"]+"',
            f'__version__ = "{version}"',
            text,
        )
    else:
        text += f'\n__version__ = "{version}"\n'
    INIT_FILE.write_text(text, encoding="utf-8")
    print(f"Updated {INIT_FILE}")


def _default_pyproject(version: str) -> str:
    """Return a minimal pyproject.toml for first-time releases."""
    return (
        "[build-system]\n"
        'requires = ["setuptools>=61.0", "wheel"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        "[project]\n"
        'name = "ide-core"\n'
        f'version = "{version}"\n'
        'description = "A modular open-source IDE core engine."\n'
        'requires-python = ">=3.10"\n'
    )


def _update_pyproject(version: str) -> None:
    """Bump the version in pyproject.toml, creating the file if missing."""
    if not PYPROJECT_FILE.exists():
        PYPROJECT_FILE.write_text(_default_pyproject(version), encoding="utf-8")
        print(f"Created {PYPROJECT_FILE}")
        return

    text = PYPROJECT_FILE.read_text(encoding="utf-8")
    new_text = re.sub(
        r'^(\s*version\s*=\s*)"[^"]+"',
        lambda m: f'{m.group(1)}"{version}"',
        text,
        flags=re.MULTILINE,
    )
    if new_text == text:
        # Add version under [project] if not present.
        if "[project]" in text:
            new_text = text.replace(
                "[project]\n",
                f'[project]\nversion = "{version}"\n',
                1,
            )
        else:
            new_text = text + f"\n[project]\nversion = \"{version}\"\n"
    PYPROJECT_FILE.write_text(new_text, encoding="utf-8")
    print(f"Updated {PYPROJECT_FILE}")


def _git_commit_and_tag(version: str) -> None:
    """Commit version bumps, create a tag, and push to origin."""
    _run_command(["git", "add", str(INIT_FILE), str(PYPROJECT_FILE)])
    _run_command(["git", "commit", "-m", f"release: v{version}"])
    _run_command(["git", "tag", f"v{version}"])
    _run_command(["git", "push", "origin", "main", "--tags"])
    print(f"Pushed tag v{version} to origin/main.")


def main() -> int:
    """Run the release workflow."""
    parser = argparse.ArgumentParser(description="Release the IDE Core project.")
    parser.add_argument("--version", help="Semantic version to release (e.g., v1.0.0)")
    args = parser.parse_args()

    _run_pytest()

    version = (args.version or _prompt_version()).lstrip("v")
    _update_init_file(version)
    _update_pyproject(version)
    _git_commit_and_tag(version)

    print(f"Release v{version} complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
