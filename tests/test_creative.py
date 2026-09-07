"""Mock-driven tests for the creative agent subsystem."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ide_core.config.settings import IDESettings
from ide_core.creative import (
    CreativeAgent,
    CreativeDomain,
    CreativeIntentEngine,
    CreativeRequest,
)
from ide_core.creative.generators.image_gen import ImageGenerator
from ide_core.creative.generators.sound_gen import SoundGenerator
from ide_core.creative.generators.video_gen import VideoGenerator
from ide_core.creative.models import CreativeTool
from ide_core.creative.tool_installer import ToolInstaller
from ide_core.multimodal.input_engine import MultimodalInputEngine
from ide_core.multimodal.models import ProcessedInput


def _settings(tmp_path):
    return IDESettings(
        creative_tools_path=str(tmp_path / "tools"),
        log_path=str(tmp_path / "ide_engine.log"),
    )


# ---------------------------------------------------------------------------
# Creative models
# ---------------------------------------------------------------------------


def test_creative_tool_defaults() -> None:
    tool = CreativeTool(
        name="ffmpeg",
        domain=CreativeDomain.VIDEO,
        description="Video encoder",
        install_command="apt-get install -y ffmpeg",
    )
    assert tool.is_installed is False


# ---------------------------------------------------------------------------
# Intent engine
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Create a logo for BudgetBuddy", CreativeDomain.LOGO),
        ("Generate a happy background music track", CreativeDomain.SOUND),
        ("Make a UI mockup for the login screen", CreativeDomain.UI_MOCKUP),
        ("Generate a screenshot of a diagram", CreativeDomain.IMAGE),
        ("Narrate this tutorial with a voiceover", CreativeDomain.VOICEOVER),
        ("Make a demo video of the app", CreativeDomain.VIDEO),
        ("Design a game asset sprite", CreativeDomain.GAME_ASSET),
    ],
)
def test_intent_engine_interpret(prompt: str, expected: CreativeDomain) -> None:
    engine = CreativeIntentEngine()
    request = engine.interpret_text(prompt)

    assert request.domain == expected
    assert request.prompt == prompt
    assert request.request_id


def test_intent_engine_extracts_style_and_options() -> None:
    engine = CreativeIntentEngine()
    request = engine.interpret_text("Create a minimal logo size:128 duration:10")

    assert request.style == "minimal"
    assert request.options["size"] == 128
    assert request.options["duration"] == 10


def test_intent_engine_accepts_processed_input() -> None:
    engine = CreativeIntentEngine()
    processed = ProcessedInput(
        input_id="m-1",
        raw_text="Make a watercolor illustration",
    )
    request = engine.interpret_text(processed)

    assert request.domain == CreativeDomain.IMAGE
    assert request.tenant_id is None
    assert request.style == "watercolor"


# ---------------------------------------------------------------------------
# Tool installer
# ---------------------------------------------------------------------------


def test_tool_installer_found_immediately(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

    installer = ToolInstaller()
    assert asyncio.run(installer.ensure_tool("ffmpeg")) is True


def test_tool_installer_auto_install_success(monkeypatch) -> None:
    which_calls = {"ffmpeg": False, "apt-get": "/usr/bin/apt-get"}

    def fake_which(name: str):
        if name == "ffmpeg" and not which_calls["ffmpeg"]:
            return None
        if name == "ffmpeg" and which_calls["ffmpeg"]:
            return "/usr/bin/ffmpeg"
        return which_calls.get(name)

    def fake_run(*args, **kwargs):
        which_calls["ffmpeg"] = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr("subprocess.run", fake_run)

    installer = ToolInstaller()
    assert asyncio.run(installer.ensure_tool("ffmpeg")) is True


def test_tool_installer_auto_install_disabled(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)

    settings = IDESettings(
        enable_auto_install=False,
        log_path="ide_engine.log",
    )
    installer = ToolInstaller(settings)
    assert asyncio.run(installer.ensure_tool("ffmpeg")) is False


def test_tool_installer_auto_install_failure(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MagicMock(returncode=1),
    )

    installer = ToolInstaller()
    assert asyncio.run(installer.ensure_tool("missing_tool")) is False


# ---------------------------------------------------------------------------
# Image generator
# ---------------------------------------------------------------------------


def test_image_generator(tmp_path) -> None:
    settings = _settings(tmp_path)
    generator = ImageGenerator(settings)

    result = asyncio.run(generator.generate("A happy robot", style="cartoon"))
    assert result.success
    assert result.domain == CreativeDomain.IMAGE
    assert result.output_path.endswith(".svg")
    assert b"A happy robot" in result.preview_data

    logo = asyncio.run(generator.generate_logo("BudgetBuddy", style="minimal"))
    assert logo.success
    assert logo.domain == CreativeDomain.LOGO
    assert b"BudgetBuddy" in logo.preview_data

    mockup = asyncio.run(generator.generate_ui_mockup("Login screen"))
    assert mockup.success
    assert mockup.domain == CreativeDomain.UI_MOCKUP
    assert b"Login screen" in mockup.preview_data


# ---------------------------------------------------------------------------
# Sound generator
# ---------------------------------------------------------------------------


def test_sound_generator(tmp_path) -> None:
    settings = _settings(tmp_path)
    generator = SoundGenerator(settings)

    sound = asyncio.run(generator.generate_sound("explosion"))
    assert sound.success
    assert sound.domain == CreativeDomain.SOUND
    assert sound.output_path.endswith(".wav")
    assert len(sound.preview_data) > 0

    music = asyncio.run(generator.generate_music("happy", duration=3))
    assert music.success
    assert music.metadata["duration_seconds"] == 3

    voice = asyncio.run(generator.generate_voiceover("Hello world", voice="alloy"))
    assert voice.success
    assert voice.domain == CreativeDomain.VOICEOVER
    assert voice.output_path.endswith(".wav")


# ---------------------------------------------------------------------------
# Video generator
# ---------------------------------------------------------------------------


def test_video_generator(tmp_path) -> None:
    settings = _settings(tmp_path)
    generator = VideoGenerator(settings)

    demo = asyncio.run(generator.generate_demo("BudgetBuddy", features=["sign in", "dashboard"]))
    assert demo.success
    assert demo.domain == CreativeDomain.VIDEO
    assert demo.output_path.endswith(".json")
    assert b"BudgetBuddy" in demo.preview_data

    tutorial = asyncio.run(generator.generate_tutorial(["open app", "click login"]))
    assert tutorial.success
    assert tutorial.domain == CreativeDomain.VIDEO
    metadata = json.loads(Path(tutorial.output_path).read_text())
    assert metadata["steps"] == ["open app", "click login"]


# ---------------------------------------------------------------------------
# CreativeAgent
# ---------------------------------------------------------------------------


def test_creative_agent_routes_logo(tmp_path) -> None:
    settings = _settings(tmp_path)
    agent = CreativeAgent(settings)
    request = CreativeRequest(
        request_id="r-1",
        domain=CreativeDomain.LOGO,
        prompt="BudgetBuddy",
        style="minimal",
    )
    result = asyncio.run(agent.execute(request))

    assert result.success
    assert result.domain == CreativeDomain.LOGO
    assert result.output_path.endswith(".svg")


def test_creative_agent_routes_sound(tmp_path) -> None:
    settings = _settings(tmp_path)
    agent = CreativeAgent(settings)
    request = CreativeRequest(
        request_id="r-2",
        domain=CreativeDomain.SOUND,
        prompt="Generate a buzz sound",
    )
    result = asyncio.run(agent.execute(request))

    assert result.success
    assert result.domain == CreativeDomain.SOUND
    assert result.output_path.endswith(".wav")


def test_creative_agent_routes_voiceover(tmp_path) -> None:
    settings = _settings(tmp_path)
    agent = CreativeAgent(settings)
    request = CreativeRequest(
        request_id="r-3",
        domain=CreativeDomain.VOICEOVER,
        prompt="Welcome to the app",
        options={"voice": "alloy"},
    )
    result = asyncio.run(agent.execute(request))

    assert result.success
    assert result.domain == CreativeDomain.VOICEOVER
    assert result.output_path.endswith(".wav")


def test_creative_agent_routes_video_tutorial(tmp_path) -> None:
    settings = _settings(tmp_path)
    agent = CreativeAgent(settings)
    request = CreativeRequest(
        request_id="r-4",
        domain=CreativeDomain.VIDEO,
        prompt="Tutorial",
        options={"kind": "tutorial", "steps": ["open app"]},
    )
    result = asyncio.run(agent.execute(request))

    assert result.success
    assert result.domain == CreativeDomain.VIDEO
    assert result.output_path.endswith(".json")


def test_creative_agent_disabled(tmp_path) -> None:
    settings = _settings(tmp_path)
    settings.enable_creative_agent = False
    agent = CreativeAgent(settings)
    request = CreativeRequest(
        request_id="r-5",
        domain=CreativeDomain.IMAGE,
        prompt="A cat",
    )
    result = asyncio.run(agent.execute(request))

    assert result.success is False
    assert "disabled" in result.message


# ---------------------------------------------------------------------------
# Multimodal-to-Creative integration
# ---------------------------------------------------------------------------


def test_multimodal_context_includes_creative_hint(tmp_path) -> None:
    settings = _settings(tmp_path)
    settings.enable_creative_agent = True
    engine = MultimodalInputEngine(settings)

    processed = ProcessedInput(
        input_id="m-creative",
        raw_text="Create a logo for BudgetBuddy in a minimal style",
        intent="create",
    )
    context = engine.to_agent_context(processed)

    assert "### Creative Intent Hint" in context
    assert "- **Domain:** logo" in context
    assert "- **Style:** minimal" in context


def test_multimodal_context_no_creative_hint_when_disabled(tmp_path) -> None:
    settings = _settings(tmp_path)
    settings.enable_creative_agent = False
    engine = MultimodalInputEngine(settings)

    processed = ProcessedInput(
        input_id="m-creative",
        raw_text="Create a logo for BudgetBuddy",
        intent="create",
    )
    context = engine.to_agent_context(processed)

    assert "Creative Intent Hint" not in context
