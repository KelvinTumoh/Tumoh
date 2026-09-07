"""Security gate for terminal and agent command execution."""

from __future__ import annotations

import logging
import shlex
from typing import Any

from ide_core.config.settings import IDESettings


class SecurityManager:
    """Enforce allow/block lists and confirmation prompts for shell commands."""

    def __init__(
        self,
        settings: IDESettings | None = None,
        audit_logger: logging.Logger | None = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._audit = audit_logger or logging.getLogger(__name__)
        self._blocked = [c.lower() for c in self._settings.blocked_shell_commands]
        self._confirmation = [
            c.lower() for c in self._settings.require_confirmation_patterns
        ]
        self._allowed = (
            [c.lower() for c in self._settings.allowed_shell_commands]
            if self._settings.allowed_shell_commands
            else None
        )

    def check_command(self, command: str, confirmed: bool = False) -> dict[str, Any]:
        """Return whether ``command`` may run and whether it needs confirmation."""
        command_lower = command.lower().strip()
        reason = ""
        requires_confirmation = False

        if self._allowed is not None:
            first_token = self._first_token(command)
            if first_token not in self._allowed:
                reason = (
                    f"Command {first_token!r} is not in the allowed command list"
                )
                self._audit.warning("Blocked command: %r - %s", command, reason)
                return {
                    "allowed": False,
                    "requires_confirmation": False,
                    "reason": reason,
                }

        for pattern in self._blocked:
            if pattern and pattern in command_lower:
                reason = f"Blocked pattern {pattern!r} found in command"
                self._audit.warning("Blocked command: %r - %s", command, reason)
                return {
                    "allowed": False,
                    "requires_confirmation": False,
                    "reason": reason,
                }

        for pattern in self._confirmation:
            if pattern and pattern in command_lower:
                requires_confirmation = True
                reason = f"Command matches confirmation pattern {pattern!r}"
                break

        allowed = not requires_confirmation or confirmed
        if requires_confirmation and not confirmed:
            reason = f"Confirmation required: {reason}"
        elif not reason:
            reason = "OK"

        self._audit.info(
            "Command decision: allowed=%s confirmed=%s command=%r reason=%s",
            allowed,
            confirmed,
            command,
            reason,
        )
        return {
            "allowed": allowed,
            "requires_confirmation": requires_confirmation,
            "reason": reason,
        }

    @staticmethod
    def _first_token(command: str) -> str:
        try:
            return shlex.split(command, posix=False)[0].lower()
        except ValueError:
            parts = command.strip().split()
            return parts[0].lower() if parts else ""
