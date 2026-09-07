"""Unit tests for the command execution security gate."""

from __future__ import annotations

from ide_core.config.settings import IDESettings
from ide_core.security import SecurityManager


def _settings(**overrides):
    return IDESettings(**overrides)


def test_allowed_command() -> None:
    sm = SecurityManager(_settings())
    result = sm.check_command("echo hello")
    assert result["allowed"] is True
    assert result["requires_confirmation"] is False


def test_blocked_command() -> None:
    sm = SecurityManager(_settings())
    result = sm.check_command("rm -rf /")
    assert result["allowed"] is False


def test_confirmation_required() -> None:
    sm = SecurityManager(_settings())
    result = sm.check_command("rm file.txt")
    assert result["allowed"] is False
    assert result["requires_confirmation"] is True


def test_confirmation_granted() -> None:
    sm = SecurityManager(_settings())
    result = sm.check_command("rm file.txt", confirmed=True)
    assert result["allowed"] is True


def test_allowlist_blocks_unknown() -> None:
    sm = SecurityManager(
        _settings(allowed_shell_commands=["echo", "python"])
    )
    assert sm.check_command("echo hi")["allowed"] is True
    assert sm.check_command("ls")["allowed"] is False
