"""End-to-end integration tests for the production IDE engine."""

import asyncio
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

from ide_core.agent.context import ContextRetriever
from ide_core.agent.memory import AgentMemory
from ide_core.agent.models import AssistantMessage, ToolCall
from ide_core.agent.orchestrator import AgentConfig, AgentOrchestrator
from ide_core.agent.tools import ToolRegistry
from ide_core.auth.manager import AuthManager, User
from ide_core.config.settings import IDESettings
from ide_core.diagnostics import DiagnosticManager
from ide_core.docs.api import OpenAPIDocs
from ide_core.document_manager import DocumentManager
from ide_core.errors.manager import ErrorManager, Severity
from ide_core.git.manager import GitManager
from ide_core.logging.logger import IDELogger
from ide_core.optimization.cache import SmartCache


class FakeLSPClient:
    """Stub LSP client for integration tests."""

    def __init__(self) -> None:
        self.diagnostics_callback = None
        self.did_open = AsyncMock()
        self.did_change = AsyncMock()
        self.did_close = AsyncMock()

    def on(self, method: str, callback) -> None:
        if method == "textDocument/publishDiagnostics":
            self.diagnostics_callback = callback


class FakeLLMClient:
    """Deterministic LLM client for integration tests."""

    def __init__(self, responses):
        self.responses = list(responses)

    async def complete(self, messages, tools) -> AssistantMessage:
        if self.responses:
            return self.responses.pop(0)
        return AssistantMessage("done")


def _init_git(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path,
        check=True,
        capture_output=True,
    )


def test_full_workflow():
    async def coro():
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            _init_git(workspace)
            (workspace / "README.md").write_text("# Project")
            subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True)

            # Configuration & auth
            settings = IDESettings(jwt_secret="x" * 32)
            auth = AuthManager(settings, api_keys={"dev-key"})
            assert auth.verify_api_key("dev-key")
            user = User(user_id="u1", name="Dev")
            token = auth.create_token(user)
            assert auth.verify_token(token) is not None

            # Logging
            log_file = workspace / "ide_engine.log"
            log_settings = IDESettings(log_path=str(log_file))
            logger = IDELogger(log_settings)
            logger.log_event("engine_start", workspace=str(workspace))
            logger.log_agent_action("plan", "agent-1", "ok", step=1)

            # Caching
            cache = SmartCache(disk_path=workspace / "cache")
            cache.set("embedding:main", [0.1, 0.2])
            assert cache.get("embedding:main") == [0.1, 0.2]

            # Error management
            errors = ErrorManager()
            errors.register(
                ValueError, lambda exc: f"handled {exc}", Severity.WARNING
            )
            assert errors.handle(ValueError("x")) == "handled x"
            assert errors.severity(ValueError("x")) == Severity.WARNING

            # Git manager
            git = GitManager(workspace)

            # Document / agent setup
            dm = DocumentManager(FakeLSPClient(), DiagnosticManager())
            diagnostics = DiagnosticManager()
            registry = ToolRegistry(workspace, dm, diagnostics)
            retriever = ContextRetriever(dm, diagnostics, registry)
            memory = AgentMemory(workspace / "memory.json")

            responses = [
                AssistantMessage(
                    "I will create the main file.",
                    [
                        ToolCall(
                            "1",
                            "write_file",
                            {"path": "main.py", "content": "print('hello integration')\n"},
                        )
                    ],
                ),
                AssistantMessage(
                    "I will stage the new file.",
                    [ToolCall("2", "run_command", {"command": "git add -A"})],
                ),
                AssistantMessage(
                    "I will commit the changes.",
                    [ToolCall("3", "run_command", {"command": "git commit -m agent_commit"})],
                ),
                AssistantMessage("Workflow complete."),
            ]

            orchestrator = AgentOrchestrator(
                FakeLLMClient(responses),
                registry,
                retriever,
                config=AgentConfig(max_iterations=5),
                agent_memory=memory,
            )

            await orchestrator.run("set up the project and commit")

            # Assertions
            assert (workspace / "main.py").read_text() == "print('hello integration')\n"

            status = await git.status()
            assert not any(s["path"] == "main.py" for s in status)

            assert log_file.exists()
            log_text = log_file.read_text()
            assert "engine_start" in log_text
            assert "agent_action" in log_text

            # Close log handlers so the temp directory can be cleaned up on Windows.
            for handler in logger._logger.handlers:
                handler.close()
                logger._logger.removeHandler(handler)

            # OpenAPI docs
            docs = OpenAPIDocs(registry).generate()
            assert "openapi" in docs
            assert any("/tools/" in p for p in docs["paths"])

    asyncio.run(coro())
