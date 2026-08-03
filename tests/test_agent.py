"""Unit tests for the autonomous AI agent engine."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from ide_core.agent.config import AgentConfig
from ide_core.agent.context import ContextRetriever
from ide_core.agent.orchestrator import (
    AgentOrchestrator,
    AssistantMessage,
    LLMClient,
    ToolCall,
)
from ide_core.agent.tools import ToolRegistry
from ide_core.diagnostics import DiagnosticManager
from ide_core.document_manager import DocumentManager


class FakeLSPClient:
    """Stub LSP client for agent tests."""

    def __init__(self) -> None:
        self.diagnostics_callback = None
        self.did_open = AsyncMock()
        self.did_change = AsyncMock()
        self.did_close = AsyncMock()

    def on(self, method: str, callback) -> None:
        if method == "textDocument/publishDiagnostics":
            self.diagnostics_callback = callback

    def publish(self, params: dict) -> None:
        if self.diagnostics_callback is not None:
            self.diagnostics_callback(params)


class FakeLLMClient(LLMClient):
    """Deterministic LLM client for orchestrator tests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def complete(self, messages, tools) -> AssistantMessage:
        self.calls += 1
        if self.responses:
            return self.responses.pop(0)
        return AssistantMessage("done")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def test_tool_registry_file_and_search():
    async def coro():
        with tempfile.TemporaryDirectory() as tmp:
            dm = DocumentManager(FakeLSPClient(), DiagnosticManager())
            diagnostics = DiagnosticManager()
            registry = ToolRegistry(tmp, dm, diagnostics)

            await registry.execute(
                "write_file",
                {"path": "helper.py", "content": "answer = 42\n"},
            )

            read = await registry.execute("read_file", {"path": "helper.py"})
            assert read["content"] == "answer = 42\n"

            search = await registry.execute("search_code", {"query": "answer"})
            assert search["count"] >= 1
            assert any("answer = 42" in m["text"] for m in search["matches"])

    asyncio.run(coro())


def test_tool_registry_run_command():
    async def coro():
        with tempfile.TemporaryDirectory() as tmp:
            dm = DocumentManager(FakeLSPClient(), DiagnosticManager())
            diagnostics = DiagnosticManager()
            registry = ToolRegistry(tmp, dm, diagnostics)

            ok = await registry.execute(
                "run_command", {"command": "python -c \"print('hello')\""}
            )
            assert ok["exit_code"] == 0
            assert "hello" in ok["stdout"]

            bad = await registry.execute(
                "run_command", {"command": "python -c \"import sys; sys.exit(1)\""}
            )
            assert bad["exit_code"] == 1

    asyncio.run(coro())


def test_tool_registry_get_diagnostics():
    async def coro():
        with tempfile.TemporaryDirectory() as tmp:
            dm = DocumentManager(FakeLSPClient(), DiagnosticManager())
            diagnostics = DiagnosticManager()
            diagnostics.update("file:///a.py", [{"message": "error"}])
            registry = ToolRegistry(tmp, dm, diagnostics)

            result = await registry.execute(
                "get_diagnostics", {"uri": "file:///a.py"}
            )
            assert result["diagnostics"] == [{"message": "error"}]

    asyncio.run(coro())


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


def test_context_retriever_assembly():
    async def coro():
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "helper.py").write_text("# everyone")

            dm = DocumentManager(FakeLSPClient(), DiagnosticManager())
            diagnostics = DiagnosticManager()
            await dm.open_document("file:///a.py", "python", "hello world")
            await dm.apply_edit("file:///a.py", 6, 11, "everyone")
            diagnostics.update("file:///a.py", [{"message": "syntax error"}])

            registry = ToolRegistry(tmp, dm, diagnostics)
            retriever = ContextRetriever(dm, diagnostics, registry)

            context = await retriever.retrieve(query="everyone")
            assert any(d["uri"] == "file:///a.py" for d in context["open_files"])
            assert context["diagnostics"]["file:///a.py"]
            assert len(context["recent_edits"]) == 1
            assert any("# everyone" in f["content"] for f in context["relevant_files"])

    asyncio.run(coro())


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def test_orchestrator_self_correction_loop():
    async def coro():
        with tempfile.TemporaryDirectory() as tmp:
            dm = DocumentManager(FakeLSPClient(), DiagnosticManager())
            diagnostics = DiagnosticManager()
            registry = ToolRegistry(tmp, dm, diagnostics)
            retriever = ContextRetriever(dm, diagnostics, registry)

            responses = [
                AssistantMessage(
                    "I'll create a failing script, then fix it.",
                    [
                        ToolCall(
                            "1", "write_file", {"path": "test.py", "content": "assert 1 == 2\n"}
                        )
                    ],
                ),
                AssistantMessage(
                    "Running the test now.",
                    [ToolCall("2", "run_command", {"command": "python test.py"})],
                ),
                AssistantMessage(
                    "Fixing the assertion.",
                    [
                        ToolCall(
                            "3",
                            "write_file",
                            {"path": "test.py", "content": "assert 1 == 1\n"},
                        )
                    ],
                ),
                AssistantMessage(
                    "Rerunning the test.",
                    [ToolCall("4", "run_command", {"command": "python test.py"})],
                ),
                AssistantMessage("The script now passes."),
            ]
            llm = FakeLLMClient(responses)
            config = AgentConfig(max_iterations=5, auto_run_tests=False)
            agent = AgentOrchestrator(llm, registry, retriever, config)

            messages = await agent.run("fix the broken test")

            # The last tool result should be a successful run_command.
            last_tool = [m for m in messages if m["role"] == "tool"][-1]
            assert json.loads(last_tool["content"])["exit_code"] == 0
            assert llm.calls == 5

    asyncio.run(coro())
