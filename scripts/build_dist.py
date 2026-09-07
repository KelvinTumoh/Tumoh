"""Build source and wheel distributions for the IDE core package."""

from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(description="Build IDE core distributions.")
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip lint/type-check/test before building.",
    )
    parser.add_argument(
        "--twine-check",
        action="store_true",
        help="Run twine check on the built distributions.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    dist_dir = project_root / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    if not args.skip_tests:
        run([sys.executable, "-m", "ruff", "check", "."])
        run([sys.executable, "-m", "mypy", "ide_core"])
        run([sys.executable, "-m", "pytest", "-m", "not integration"])

    run([sys.executable, "-m", "build", str(project_root)])

    if args.twine_check:
        run([sys.executable, "-m", "twine", "check", str(dist_dir / "*")])

    print(f"Distributions built in {dist_dir}")


if __name__ == "__main__":
    main()
