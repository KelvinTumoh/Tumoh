"""Autonomous agent orchestrator with structured function calling."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ide_core.config.settings import IDESettings
from ide_core.personality import FriendPersonality
from ide_core.terminal import TerminalManager

from .config import AgentConfig
from .context import ContextRetriever
from .memory import AgentMemory
from .models import AssistantMessage, LLMClient, ToolCall
from .operations import EditBatcher
from .parallel import ParallelToolRunner
from .semantic_search import SemanticSearch
from .tools import ToolRegistry


class AgentOrchestrator:
    """Drives an iterative tool loop and self-corrects on errors."""

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        context_retriever: ContextRetriever,
        config: Optional[AgentConfig] = None,
        terminal_manager: Optional[TerminalManager] = None,
        agent_memory: Optional[AgentMemory] = None,
        edit_batcher: Optional[EditBatcher] = None,
        semantic_search: Optional[SemanticSearch] = None,
        ide_settings: Optional[IDESettings] = None,
    ) -> None:
        self._llm = llm_client
        self._tools = tool_registry
        self._context = context_retriever
        self._config = config or AgentConfig()
        self._terminal = terminal_manager
        self._memory = agent_memory
        self._batcher = edit_batcher
        self._semantic = semantic_search
        self._ide_settings = ide_settings or IDESettings()

    async def run(self, prompt: str) -> List[dict]:
        """Run the agent loop until the LLM stops calling tools or max iterations."""
        system = self._build_system_prompt()
        messages: List[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        context = await self._build_context(query=prompt)
        messages.append(
            {"role": "user", "content": json.dumps(context, default=str)}
        )

        runner = ParallelToolRunner(self._tools)
        for _ in range(self._config.max_iterations):
            response = await self._llm.complete(
                messages, self._tools.get_schemas()
            )

            if not response.tool_calls:
                messages.append(
                    {"role": "assistant", "content": response.content}
                )
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in response.tool_calls
                    ],
                }
            )

            results = await runner.run(response.tool_calls)
            for tc, result in zip(response.tool_calls, results, strict=False):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str),
                    }
                )

            if self._memory is not None:
                self._memory.remember(
                    f"iteration_{self._memory.all().__len__() + 1}",
                    {
                        "tool_calls": [tc.name for tc in response.tool_calls],
                        "results": results,
                    },
                )

        return messages

    async def _build_context(self, query: Optional[str] = None) -> Dict[str, Any]:
        """Assemble the full agent context, including terminal and memory."""
        context = await self._context.retrieve(query=query)

        if self._terminal is not None:
            context["terminal_recent_output"] = self._capture_terminal_context()

        if self._memory is not None:
            context["agent_memory"] = self._memory.all()

        if self._semantic is not None and query is not None:
            # If an embedder is not configured, fall back to text search.
            search_results = self._semantic.search_text(query)
            context["semantic_search"] = [
                {"key": key, "score": score} for key, score in search_results
            ]

        return context

    def _capture_terminal_context(self, lines: int = 20) -> str:
        """Return the most recent terminal output for the prompt."""
        if self._terminal is None:
            return ""
        return self._terminal.get_recent_output(lines)

    def _build_system_prompt(self) -> str:
        base = (
            "You are an autonomous coding assistant running inside a custom IDE. "
            "You have access to workspace tools. Call one or more tools in each "
            "turn. When the task is complete, respond with a short summary and no "
            "tool calls."
        )
        if self._config.auto_run_tests:
            base += (
                " After making code changes, run the relevant test command "
                "(e.g. `python -m pytest`) and fix any failures you find."
            )
        if self._ide_settings.enable_friend_personality:
            base += " " + FriendPersonality.get_system_directive()
        return base
