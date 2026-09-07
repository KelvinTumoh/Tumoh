"""Unit tests for terminal, project, and advanced agent operations."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

from ide_core.agent.context import ContextRetriever
from ide_core.agent.memory import AgentMemory
from ide_core.agent.operations import EditBatcher
from ide_core.agent.orchestrator import (
    AgentConfig,
    AgentOrchestrator,
    AssistantMessage,
    ToolCall,
)
from ide_core.agent.parallel import ParallelToolRunner
from ide_core.agent.semantic_search import SemanticSearch
from ide_core.agent.tools import ToolRegistry
from ide_core.diagnostics import DiagnosticManager
from ide_core.document_manager import DocumentManager
from ide_core.project.manager import ProjectManager
from ide_core.terminal import TerminalManager


class FakeLSPClient:
    """Stub LSP client for project tests."""

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


class FakeLLMClient:
    """Deterministic LLM client for project/orchestrator tests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.messages_seen = []

    async def complete(self, messages, tools) -> AssistantMessage:
        self.messages_seen.append(list(messages))
        if self.responses:
            return self.responses.pop(0)
        return AssistantMessage("done")


# ---------------------------------------------------------------------------
# Terminal
# ---------------------------------------------------------------------------


def test_terminal_streaming():
    async def coro():
        outputs = []

        def on_output(data):
            outputs.append(data)

        term = TerminalManager(["python", "-i"], output_callback=on_output)
        await term.start()
        try:
            await term.write("print('hello_agent')\n")
            await asyncio.sleep(0.3)
            recent = term.get_recent_output(10)
            assert "hello_agent" in recent
        finally:
            await term.stop()

    asyncio.run(coro())


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


def test_project_tree_respects_gitignore():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "main.py").write_text("x")
        (root / "keep.txt").write_text("x")
        (root / "ignored.pyc").write_text("x")
        (root / "node_modules").mkdir()
        (root / "node_modules" / "pkg.js").write_text("x")
        (root / ".gitignore").write_text("*.pyc\n__pycache__/\n")

        pm = ProjectManager(root)
        tree = pm.tree()

        def collect_paths(node, acc):
            if node.get("type") == "file":
                acc.append(node["path"])
            for child in node.get("children", []):
                collect_paths(child, acc)

        paths = []
        collect_paths(tree, paths)

        assert "main.py" in paths
        assert "keep.txt" in paths
        assert "ignored.pyc" not in paths
        assert not any("node_modules" in p for p in paths)


def test_project_environment_and_git_status():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "pyproject.toml").write_text("[project]")

        pm = ProjectManager(root)
        env = pm.environment()
        assert env["python"] is True


# ---------------------------------------------------------------------------
# Edit Batcher
# ---------------------------------------------------------------------------


def test_atomic_edit_rollback():
    async def coro():
        with tempfile.TemporaryDirectory() as tmp:
            dm = DocumentManager(FakeLSPClient(), DiagnosticManager())
            diagnostics = DiagnosticManager()
            registry = ToolRegistry(tmp, dm, diagnostics)
            batcher = EditBatcher(registry)

            (Path(tmp) / "a.py").write_text("original a")

            result = await batcher.apply(
                [
                    {"path": "a.py", "content": "changed a"},
                    {"path": "../outside/b.py", "content": "bad"},
                ]
            )

            assert result["success"] is False
            assert Path(tmp, "a.py").read_text() == "original a"

    asyncio.run(coro())


# ---------------------------------------------------------------------------
# Semantic Search
# ---------------------------------------------------------------------------


def test_semantic_search_caching():
    async def coro():
        calls = 0

        async def embed(text):
            nonlocal calls
            calls += 1
            # Very simple deterministic vector: one-hot-ish token counts.
            if "python" in text.lower():
                return [1.0, 0.0, 0.0]
            if "test" in text.lower():
                return [0.0, 1.0, 0.0]
            return [0.0, 0.0, 1.0]

        search = SemanticSearch(embed=embed)
        await search.index({
            "python_intro": "This is a python file",
            "test_file": "Unit tests for the project",
        })

        query = [1.0, 0.0, 0.0]  # looking for python-ish
        results = search.search(query, top_k=1)
        assert results[0][0] == "python_intro"
        assert calls == 2

        # Re-indexing should use cache and not call embed again.
        await search.index({"python_intro": "This is a python file"})
        assert calls == 2

    asyncio.run(coro())


# ---------------------------------------------------------------------------
# Agent Memory
# ---------------------------------------------------------------------------


def test_agent_memory_persistence():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp, "memory.json")
        mem = AgentMemory(path)
        mem.remember("decision", "use pytest")

        fresh = AgentMemory(path)
        assert fresh.recall("decision") == "use pytest"


# ---------------------------------------------------------------------------
# Parallel Tool Runner
# ---------------------------------------------------------------------------


def test_parallel_tool_execution():
    async def coro():
        with tempfile.TemporaryDirectory() as tmp:
            dm = DocumentManager(FakeLSPClient(), DiagnosticManager())
            diagnostics = DiagnosticManager()
            registry = ToolRegistry(tmp, dm, diagnostics)
            runner = ParallelToolRunner(registry)

            calls = [
                ToolCall("1", "write_file", {"path": "a.txt", "content": "A"}),
                ToolCall("2", "write_file", {"path": "b.txt", "content": "B"}),
            ]
            results = await runner.run(calls)

            assert all("bytes_written" in r for r in results)
            assert Path(tmp, "a.txt").read_text() == "A"
            assert Path(tmp, "b.txt").read_text() == "B"

    asyncio.run(coro())


# ---------------------------------------------------------------------------
# Orchestrator context capture
# ---------------------------------------------------------------------------


def test_orchestrator_captures_terminal_and_memory_context():
    async def coro():
        with tempfile.TemporaryDirectory() as tmp:
            dm = DocumentManager(FakeLSPClient(), DiagnosticManager())
            diagnostics = DiagnosticManager()
            registry = ToolRegistry(tmp, dm, diagnostics)
            retriever = ContextRetriever(dm, diagnostics, registry)

            term = TerminalManager(["python", "-i"])
            await term.start()
            try:
                await term.write("print('term_capture')\n")
                await asyncio.sleep(0.3)
            finally:
                await term.stop()

            memory = AgentMemory(Path(tmp, "memory.json"))
            memory.remember("insight", "shell is ready")

            llm = FakeLLMClient([AssistantMessage("I have the context.")])
            config = AgentConfig(max_iterations=2)
            orchestrator = AgentOrchestrator(
                llm,
                registry,
                retriever,
                config=config,
                terminal_manager=term,
                agent_memory=memory,
            )

            await orchestrator.run("inspect workspace")

            context_message = llm.messages_seen[0][-1]["content"]
            assert "term_capture" in context_message
            assert "insight" in context_message

    asyncio.run(coro())
