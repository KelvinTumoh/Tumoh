"""Shared agent data models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ToolCall:
    """A single tool call requested by the LLM."""

    id: str
    name: str
    arguments: Dict[str, any]


@dataclass
class AssistantMessage:
    """A response from the LLM, optionally containing tool calls."""

    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)


class LLMClient(ABC):
    """Abstract adapter for an LLM that supports function calling."""

    @abstractmethod
    async def complete(
        self, messages: List[dict], tools: List[dict]
    ) -> AssistantMessage:
        """Request the next assistant message from the LLM."""
