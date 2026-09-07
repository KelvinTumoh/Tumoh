"""Structured JSON logging for the IDE engine."""

from __future__ import annotations

import json
import logging
import logging.handlers
from pathlib import Path
from typing import Any

from ide_core.config.settings import IDESettings


class _JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "event": record.getMessage(),
            "source": record.name,
        }
        if hasattr(record, "details"):
            payload["details"] = record.details
        return json.dumps(payload, default=str)


class IDELogger:
    """Rotating, structured JSON logger for events and agent actions."""

    def __init__(self, settings: IDESettings | None = None) -> None:
        self._settings = settings or IDESettings()
        self._logger = logging.getLogger("ide_engine")
        self._logger.setLevel(getattr(logging, self._settings.log_level.upper(), logging.INFO))
        self._logger.handlers.clear()

        Path(self._settings.log_path).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            self._settings.log_path,
            maxBytes=5_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(_JsonFormatter())
        self._logger.addHandler(handler)

    def log_event(self, event: str, **details: Any) -> None:
        """Log a generic IDE event with structured details."""
        extra = {"details": details} if details else {}
        self._logger.info(event, extra=extra)

    def log_agent_action(
        self, action: str, agent_id: str, outcome: str, **details: Any
    ) -> None:
        """Log an autonomous agent action."""
        extra = {
            "details": {"agent_id": agent_id, "outcome": outcome, **details}
        }
        self._logger.info(f"agent_action: {action}", extra=extra)
