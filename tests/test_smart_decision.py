"""Tests for the smart decision subsystem."""

from __future__ import annotations

import asyncio

import pytest

from ide_core.config.settings import IDESettings
from ide_core.creative import CreativeAgent, CreativeDomain, CreativeRequest
from ide_core.smart_decision import (
    DecisionContext,
    DecisionLearner,
    DecisionOption,
    DecisionResult,
    OptionScorer,
    SmartAssistant,
    SmartChooser,
)


def _settings(tmp_path):
    return IDESettings(
        log_path=str(tmp_path / "ide_engine.log"),
        preference_storage_path=str(tmp_path / "preferences"),
    )


def test_decision_option_defaults():
    option = DecisionOption(option_id="o1", name="A", description="desc")
    assert option.score == 0.0
    assert option.metadata == {}


def test_decision_context_defaults():
    ctx = DecisionContext(user_id="u1", tenant_id="t1")
    assert ctx.project_type == "general"
    assert ctx.history == []


def test_option_scorer_deterministic():
    scorer = OptionScorer()
    option = DecisionOption(
        option_id="o1",
        name="A",
        description="",
        metadata={"quality": 1.0, "speed": 1.0, "style": "minimal"},
    )
    ctx = DecisionContext(
        user_id="u1",
        tenant_id="t1",
        project_type="minimal",
        creative_domain="image",
    )
    s1 = scorer.score_option(option, ctx)
    option.score = 0.0
    s2 = scorer.score_option(option, ctx)
    assert s1 == s2
    assert 0.0 <= s1 <= 1.0
    assert s1 > 0.0


def test_option_scorer_learned_weights():
    scorer = OptionScorer()
    option = DecisionOption(
        option_id="o1",
        name="A",
        description="",
        metadata={
            "quality": 0.0,
            "speed": 0.0,
            "style": "minimal",
            "domain": "image",
            "tags": ["minimal"],
        },
    )
    ctx = DecisionContext(
        user_id="u1",
        tenant_id="t1",
        project_type="minimal",
        creative_domain="image",
    )
    learned = {"quality": 0.0, "speed": 0.0, "preference": 0.0, "style": 1.0}
    score = scorer.score_option(option, ctx, learned)
    assert score == 1.0


def test_smart_chooser_ranking(tmp_path):
    settings = _settings(tmp_path)
    chooser = SmartChooser(settings=settings)
    options = [
        DecisionOption(
            option_id="a",
            name="A",
            description="",
            metadata={"quality": 0.2, "speed": 0.5, "style": "general"},
        ),
        DecisionOption(
            option_id="b",
            name="B",
            description="",
            metadata={"quality": 0.9, "speed": 0.9, "style": "general"},
        ),
    ]
    ctx = DecisionContext(user_id="u1", tenant_id="t1")
    result = asyncio.run(chooser.choose_best(options, ctx))
    assert result.chosen_option.option_id == "b"
    assert len(result.alternatives) == 1
    assert result.explanation_level == "friendly"
    assert result.reason


@pytest.mark.parametrize("level", ["friendly", "detailed", "minimal"])
def test_smart_chooser_explanation_levels(tmp_path, level):
    settings = _settings(tmp_path)
    settings.decision_explain_level = level
    chooser = SmartChooser(settings=settings)
    options = [
        DecisionOption(option_id="a", name="A", description="", metadata={"quality": 0.1}),
        DecisionOption(option_id="b", name="B", description="", metadata={"quality": 0.9}),
    ]
    ctx = DecisionContext(user_id="u1", tenant_id="t1")
    result = asyncio.run(chooser.choose_best(options, ctx))
    assert result.explanation_level == level
    assert result.reason


def test_smart_assistant_explain_and_alternatives(tmp_path):
    settings = _settings(tmp_path)
    assistant = SmartAssistant(settings)
    options = [
        DecisionOption(option_id="a", name="A", description="", metadata={"quality": 0.2}),
        DecisionOption(option_id="b", name="B", description="", metadata={"quality": 0.8}),
        DecisionOption(option_id="c", name="C", description="", metadata={"quality": 0.5}),
    ]
    ctx = DecisionContext(user_id="u1", tenant_id="t1")
    result = asyncio.run(assistant.decide(options, ctx))
    assert result.chosen_option.option_id == "b"
    alts = assistant.get_alternatives(result)
    assert len(alts) == 2
    explain = assistant.explain_decision(result)
    assert result.chosen_option.name in explain


def test_decision_learner_multitenant_isolation(tmp_path):
    settings = _settings(tmp_path)
    learner = DecisionLearner(settings)
    asyncio.run(learner.learn_from_feedback("tenant-a", "user-1", "d-1", "minimal", 5.0))
    asyncio.run(learner.learn_from_feedback("tenant-b", "user-1", "d-1", "bold", 2.0))
    a = asyncio.run(learner.get_user_preferences("tenant-a", "user-1"))
    b = asyncio.run(learner.get_user_preferences("tenant-b", "user-1"))
    assert a["style_preferences"]["minimal"] > 0.5
    assert b["style_preferences"]["bold"] < 0.5
    assert a != b


def test_decision_learner_feedback_updates_weights(tmp_path):
    settings = _settings(tmp_path)
    learner = DecisionLearner(settings)
    before = asyncio.run(learner.get_user_preferences("t1", "u1"))
    asyncio.run(learner.learn_from_feedback("t1", "u1", "d-1", "minimal", 5.0))
    after = asyncio.run(learner.get_user_preferences("t1", "u1"))
    assert (
        after["style_preferences"]["minimal"]
        > before["style_preferences"].get("minimal", 0.5)
    )
    assert "d-1" in [f["decision_id"] for f in after["feedback"]]
    assert "feedback" in after


def test_smart_assistant_feature_flag_disabled(tmp_path):
    settings = _settings(tmp_path)
    settings.enable_smart_decisions = False
    assistant = SmartAssistant(settings)
    options = [
        DecisionOption(option_id="a", name="A", description="", metadata={"quality": 0.9}),
        DecisionOption(option_id="b", name="B", description="", metadata={"quality": 0.1}),
    ]
    ctx = DecisionContext(user_id="u1", tenant_id="t1")
    result = asyncio.run(assistant.decide(options, ctx))
    assert result.chosen_option.option_id == "a"
    assert "disabled" in result.reason.lower()


def test_creative_agent_smart_decision_enabled(tmp_path):
    settings = _settings(tmp_path)
    agent = CreativeAgent(settings)
    request = CreativeRequest(
        request_id="r-smart",
        domain=CreativeDomain.LOGO,
        prompt="BudgetBuddy",
        style="minimal",
        options={
            "user_id": "u1",
            "project_type": "branding",
            "candidates": [
                {
                    "option_id": "logo-bold",
                    "name": "Bold",
                    "description": "A bold logo",
                    "preview_url_or_path": str(tmp_path / "bold.svg"),
                    "metadata": {"style": "bold", "quality": 0.4},
                },
                {
                    "option_id": "logo-minimal",
                    "name": "Minimal",
                    "description": "A minimal logo",
                    "preview_url_or_path": str(tmp_path / "minimal.svg"),
                    "metadata": {"style": "minimal", "quality": 0.9},
                },
            ],
        },
    )
    result = asyncio.run(agent.execute(request))
    assert result.success
    assert result.domain == CreativeDomain.LOGO
    assert "smart_decision_id" in result.metadata
    assert result.metadata["chosen_option_score"] > 0.0


def test_creative_agent_smart_decision_disabled(tmp_path):
    settings = _settings(tmp_path)
    settings.enable_smart_decisions = False
    agent = CreativeAgent(settings)
    request = CreativeRequest(
        request_id="r-smart",
        domain=CreativeDomain.LOGO,
        prompt="BudgetBuddy",
        style="minimal",
        options={
            "candidates": [
                {
                    "option_id": "logo-bold",
                    "name": "Bold",
                    "description": "A bold logo",
                    "preview_url_or_path": str(tmp_path / "bold.svg"),
                    "metadata": {"style": "bold", "quality": 0.4},
                },
            ],
        },
    )
    result = asyncio.run(agent.execute(request))
    assert result.success
    assert result.domain == CreativeDomain.LOGO
    assert "smart_decision_id" not in result.metadata
    assert result.output_path.endswith(".svg")
