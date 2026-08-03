"""Concurrent execution of independent tool calls."""

from __future__ import annotations

import asyncio
from typing import List

from .models import ToolCall
from .tools import ToolRegistry


class ParallelToolRunner:
    """Execute a list of tool calls concurrently via ``asyncio.gather``."""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def run(self, calls: List[ToolCall]) -> List[dict]:
        """Run every tool call in parallel and return results in the same order."""

        async def _run(call: ToolCall) -> dict:
            return await self._tools.execute(call.name, call.arguments)

        return await asyncio.gather(*(_run(c) for c in calls))
