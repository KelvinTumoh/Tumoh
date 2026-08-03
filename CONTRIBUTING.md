# Contributing to IDE Core

Thank you for your interest in contributing! This document outlines how to propose changes, style code, and run the test suite.

## Code Style

- Follow [PEP 8](https://peps.python.org/pep-0008/).
- Use type hints and add `from __future__ import annotations` at the top of each module.
- Write descriptive docstrings for classes, functions, and modules.
- Keep functions focused and under ~60 lines where practical.
- Prefer composition over large inheritance trees.

## Pull Request Guidelines

1. Fork the repository and create a feature branch (`git checkout -b feature/my-change`).
2. Make focused, minimal changes with clear commit messages.
3. Add or update tests for new functionality.
4. Run the full test suite locally: `pytest`.
5. Ensure CI passes on all matrix combinations (Python 3.10/3.11, Ubuntu/Windows).
6. Open a pull request with a clear description, referencing any related issue.

## Running Tests

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
pytest
```

For verbose output:

```bash
pytest -v
```

## Release Process

Maintainers run `python scripts/release.py` after all tests pass and a semantic version is decided.
