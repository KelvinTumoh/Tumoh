"""Centralized error management with severity and recovery strategies."""

from __future__ import annotations

from collections.abc import Callable
from enum import IntEnum
from typing import Any


class Severity(IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class ErrorManager:
    """Register per-exception recovery strategies and dispatch errors."""

    def __init__(self) -> None:
        self._strategies: dict[type[BaseException], Callable[[BaseException], Any]] = {}
        self._severity_map: dict[type[BaseException], Severity] = {}

    def register(
        self,
        exc_type: type[BaseException],
        handler: Callable[[BaseException], Any],
        severity: Severity = Severity.ERROR,
    ) -> Callable[[BaseException], Any]:
        """Register a recovery handler for ``exc_type``."""
        self._strategies[exc_type] = handler
        self._severity_map[exc_type] = severity
        return handler

    def handle(self, exc: BaseException) -> Any | None:
        """Dispatch an exception to its registered handler, if any."""
        for exc_type in type(exc).__mro__:
            if exc_type in self._strategies:
                return self._strategies[exc_type](exc)
        return None

    def severity(self, exc: BaseException) -> Severity:
        """Return the configured severity for ``exc`` or ``ERROR`` by default."""
        for exc_type in type(exc).__mro__:
            if exc_type in self._severity_map:
                return self._severity_map[exc_type]
        return Severity.ERROR
