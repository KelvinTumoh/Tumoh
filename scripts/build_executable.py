"""Build a standalone executable bundle with PyInstaller."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    """Run a command and stream output."""
    print(" ".join(cmd))
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a standalone IDE core executable.")
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Build a single executable file instead of a directory bundle.",
    )
    parser.add_argument(
        "--name",
        default="ide-core",
        help="Name of the output executable.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    frontend_dir = project_root / "frontend"
    entrypoint = project_root / "ide_core" / "server.py"

    if not frontend_dir.exists():
        print(f"Frontend directory not found: {frontend_dir}", file=sys.stderr)
        sys.exit(1)
    if not entrypoint.exists():
        print(f"Entrypoint not found: {entrypoint}", file=sys.stderr)
        sys.exit(1)

    dist_dir = project_root / "dist-exe"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    sep = os.pathsep
    pyinstaller = [sys.executable, "-m", "PyInstaller"]
    base_cmd = [
        "--name",
        args.name,
        "--console",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist_dir / "app"),
        "--workpath",
        str(dist_dir / "build"),
        "--specpath",
        str(dist_dir),
        "--add-data",
        f"{frontend_dir}{sep}frontend",
    ]
    if args.onefile:
        base_cmd.append("--onefile")
    else:
        base_cmd.append("--onedir")

    run(pyinstaller + base_cmd + [str(entrypoint)])
    print(f"Executable built in {dist_dir / 'app'}")


if __name__ == "__main__":
    main()
