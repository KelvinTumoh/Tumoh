"""Release asset verification tests."""

from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_readme_exists_and_has_required_sections() -> None:
    path = ROOT / "README.md"
    assert path.exists(), "README.md is missing"
    text = path.read_text(encoding="utf-8")
    assert text, "README.md is empty"
    assert "# " in text, "README.md is missing a top-level heading"
    assert "quickstart" in text.lower(), "README.md is missing a Quickstart section"
    assert "architecture" in text.lower(), "README.md is missing an Architecture section"


def test_license_exists_and_is_mit() -> None:
    path = ROOT / "LICENSE"
    assert path.exists(), "LICENSE is missing"
    text = path.read_text(encoding="utf-8")
    assert text, "LICENSE is empty"
    assert "MIT" in text, "LICENSE missing MIT text"
    assert "Permission is hereby granted" in text, "LICENSE missing standard grant"


def test_contributing_exists_and_has_guidelines() -> None:
    path = ROOT / "CONTRIBUTING.md"
    assert path.exists(), "CONTRIBUTING.md is missing"
    text = path.read_text(encoding="utf-8")
    assert text, "CONTRIBUTING.md is empty"
    assert "pytest" in text.lower(), "CONTRIBUTING.md missing test instructions"
    assert (
        "pull request" in text.lower() or "pr" in text.lower()
    ), "CONTRIBUTING.md missing PR guidelines"


def test_github_ci_workflow_exists_and_runs_pytest_matrix() -> None:
    path = ROOT / ".github" / "workflows" / "ci.yml"
    assert path.exists(), ".github/workflows/ci.yml is missing"
    text = path.read_text(encoding="utf-8")
    assert text, "ci.yml is empty"
    assert "pytest" in text, "ci.yml does not run pytest"
    assert "matrix" in text, "ci.yml does not define a matrix"
    assert "3.10" in text or "3.11" in text, "ci.yml missing Python versions"
    assert "ubuntu" in text.lower() or "windows" in text.lower(), "ci.yml missing OS matrix"
