"""Proactive, rate-limited help suggestions for IDE friction points."""

from __future__ import annotations

import time
from typing import Any, Optional


class ProactiveHelper:
    """Detects workflow friction and offers non-intrusive assistance."""

    def __init__(self, suggestion_cooldown: float = 30.0) -> None:
        self._suggestion_cooldown = max(0.0, suggestion_cooldown)
        self._last_suggestion_time = 0.0

    def _can_suggest(self) -> bool:
        return (
            time.monotonic() - self._last_suggestion_time
        ) >= self._suggestion_cooldown

    def _mark_suggestion(self) -> None:
        self._last_suggestion_time = time.monotonic()

    def analyze_workflow(
        self, action: str, history: list[dict[str, Any]]
    ) -> Optional[str]:
        """Detect patterns like repeated failures, rapid saves, or LSP squigglies."""
        if action == "build" and len(history) >= 3:
            recent = history[-3:]
            if all(h.get("success") is False for h in recent):
                return "repeated_build_failures"

        if action == "save" and len(history) >= 2:
            recent = history[-2:]
            timestamps = [
                h.get("timestamp") for h in recent if h.get("timestamp") is not None
            ]
            if len(timestamps) == 2 and abs(timestamps[1] - timestamps[0]) <= 5.0:
                return "rapid_manual_saves"

        if action == "lsp" and history:
            latest = history[-1]
            diagnostics = latest.get("diagnostics", [])
            if any(d.get("severity") == "error" for d in diagnostics):
                return "unhandled_lsp_errors"

        return None

    def suggest_help(
        self, action: str, context: dict[str, Any]
    ) -> Optional[str]:
        """Generate a non-intrusive help offer when a pattern is detected."""
        if not self._can_suggest():
            return None

        history = context.get("history", [])
        pattern = self.analyze_workflow(action, history)

        if pattern == "repeated_build_failures":
            self._mark_suggestion()
            return (
                "Looks like the build is struggling. Want me to take a closer look?"
            )

        if pattern == "rapid_manual_saves":
            self._mark_suggestion()
            return (
                "You're saving fast! Want me to format or run a quick check?"
            )

        diagnostics = context.get("diagnostics", [])
        if any(d.get("severity") == "error" for d in diagnostics):
            self._mark_suggestion()
            return (
                "I notice some red squigglies. Want a hand sorting them out?"
            )

        if self.detect_frustration(context.get("error_history", [])):
            self._mark_suggestion()
            return (
                "I see a few errors in a row. Want me to help pinpoint the cause?"
            )

        return None

    def detect_frustration(self, error_history: list[dict[str, Any]]) -> bool:
        """Return True when multiple consecutive errors occur."""
        if len(error_history) < 3:
            return False
        return all(h.get("error") is True or h.get("success") is False for h in error_history[-3:])
