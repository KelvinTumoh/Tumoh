"""Agent runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentConfig:
    """Settings for the autonomous agent."""

    model: str = "gpt-4o"
    temperature: float = 0.2
    max_iterations: int = 10
    auto_run_tests: bool = True
    reasoning_effort: str = "medium"
