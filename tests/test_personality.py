"""Tests for the friend personality subsystem."""

from __future__ import annotations

from ide_core.config.settings import IDESettings
from ide_core.personality import (
    Celebrator,
    FriendMemory,
    FriendPersonality,
    Greeter,
    Mood,
    PersonalityTrait,
    ProactiveHelper,
    UserState,
)


def _settings(tmp_path):
    return IDESettings(
        log_path=str(tmp_path / "ide_engine.log"),
        personality_storage_path=str(tmp_path / "personality"),
    )


def test_mood_values():
    assert Mood.CHEERFUL.value == "cheerful"
    assert Mood.ENCOURAGING.value == "encouraging"
    assert set(Mood) == {
        Mood.CHEERFUL,
        Mood.ENCOURAGING,
        Mood.HELPFUL,
        Mood.SILLY,
        Mood.EMPATHETIC,
    }


def test_user_state_defaults():
    state = UserState(user_id="u1", tenant_id="t1")
    assert state.greeting_count == 0
    assert state.friendship_level == 1.0
    assert state.last_interaction == ""
    assert state.achievements == []
    assert state.preferences == {}


def test_personality_trait_clamps_value():
    low = PersonalityTrait("p", -0.5)
    high = PersonalityTrait("p", 2.0)
    normal = PersonalityTrait("p", 0.7)
    assert low.value == 0.0
    assert high.value == 1.0
    assert normal.value == 0.7


def test_greeter_time_of_day():
    greeter = Greeter()
    state = UserState(user_id="u1", tenant_id="t1", friendship_level=1.0)
    morning = greeter.get_greeting("morning", state)
    afternoon = greeter.get_greeting("afternoon", state)
    evening = greeter.get_greeting("evening", state)
    night = greeter.get_greeting("night", state)
    assert "Good morning" in morning
    assert "Good afternoon" in afternoon
    assert "Good evening" in evening
    assert "Working late" in night or "Still up coding" in night or "Good night" in night


def test_greeter_friendship_scaled():
    greeter = Greeter()
    low = UserState(user_id="u1", tenant_id="t1", friendship_level=1.0)
    high = UserState(user_id="u1", tenant_id="t1", friendship_level=5.0)
    low_greeting = greeter.get_greeting("morning", low)
    high_greeting = greeter.get_greeting("morning", high)
    assert low_greeting != high_greeting or "morning" in high_greeting
    assert low_greeting.startswith("Good morning") or "Rise" in low_greeting


def test_greeter_farewell():
    greeter = Greeter()
    state = UserState(user_id="u1", tenant_id="t1")
    farewell = greeter.get_farewell(state)
    assert "u1" in farewell
    assert any(phrase in farewell for phrase in ["Catch you later", "Happy coding", "See you next time", "Take care"])


def test_greeter_welcome_back():
    greeter = Greeter()
    state = UserState(
        user_id="u1", tenant_id="t1", last_interaction="2026-08-03T20:00:00"
    )
    welcome = greeter.get_welcome_back(state)
    assert "u1" in welcome
    assert "Welcome back" in welcome or "again" in welcome
    assert "last session" in welcome


def test_celebrator_achievement():
    celeb = Celebrator()
    state = UserState(user_id="u1", tenant_id="t1")
    test_msg = celeb.celebrate("test_pass", state)
    build_msg = celeb.celebrate("build_success", state)
    streak_msg = celeb.celebrate("streak", state)
    assert "u1" in test_msg
    assert "u1" in build_msg
    assert "u1" in streak_msg
    assert "passed" in test_msg.lower() or "green" in test_msg.lower()
    assert "succeeded" in build_msg.lower() or "build" in build_msg.lower()
    assert "streak" in streak_msg.lower()


def test_celebrator_encouragement():
    celeb = Celebrator()
    state = UserState(user_id="u1", tenant_id="t1")
    test_fail = celeb.get_encouragement("test_failure", state)
    term_err = celeb.get_encouragement("terminal_error", state)
    assert "u1" in test_fail
    assert "u1" in term_err
    assert "failure" in test_fail.lower() or "debug" in test_fail.lower()
    assert "error" in term_err.lower() or "red" in term_err.lower()


def test_proactive_helper_repeated_build_failures():
    helper = ProactiveHelper()
    history = [
        {"success": False},
        {"success": False},
        {"success": False},
    ]
    assert helper.analyze_workflow("build", history) == "repeated_build_failures"


def test_proactive_helper_rapid_saves():
    helper = ProactiveHelper()
    history = [
        {"timestamp": 0.0},
        {"timestamp": 3.0},
    ]
    assert helper.analyze_workflow("save", history) == "rapid_manual_saves"


def test_proactive_helper_lsp_errors():
    helper = ProactiveHelper()
    history = [
        {"diagnostics": [{"severity": "warning"}]},
        {"diagnostics": [{"severity": "error"}]},
    ]
    assert helper.analyze_workflow("lsp", history) == "unhandled_lsp_errors"


def test_proactive_helper_suggest_help_rate_limited():
    helper = ProactiveHelper(suggestion_cooldown=60.0)
    context = {
        "history": [{"success": False}] * 3,
    }
    first = helper.suggest_help("build", context)
    assert first is not None
    assert "build" in first.lower() or "look" in first.lower()
    second = helper.suggest_help("build", context)
    assert second is None


def test_proactive_helper_detect_frustration():
    helper = ProactiveHelper()
    errors = [{"success": False}, {"success": False}, {"success": False}]
    assert helper.detect_frustration(errors) is True
    assert helper.detect_frustration(errors[:2]) is False
    assert helper.detect_frustration([{"success": True}] * 3) is False


def test_friend_memory_preferences(tmp_path):
    settings = _settings(tmp_path)
    memory = FriendMemory(settings)
    memory.remember_preference("t1", "u1", "theme", "dark")
    assert memory.get_preference("t1", "u1", "theme") == "dark"
    assert memory.get_preference("t1", "u1", "missing") is None


def test_friend_memory_multitenant_isolation(tmp_path):
    settings = _settings(tmp_path)
    memory = FriendMemory(settings)
    memory.remember_preference("tenant-a", "user-1", "theme", "dark")
    memory.remember_preference("tenant-b", "user-1", "theme", "light")
    a = memory.get_preference("tenant-a", "user-1", "theme")
    b = memory.get_preference("tenant-b", "user-1", "theme")
    assert a == "dark"
    assert b == "light"
    state_a = memory.get_user_state("tenant-a", "user-1")
    state_b = memory.get_user_state("tenant-b", "user-1")
    assert state_a.tenant_id != state_b.tenant_id
    assert state_a.preferences != state_b.preferences


def test_friend_memory_increment_friendship_and_persist(tmp_path):
    settings = _settings(tmp_path)
    memory = FriendMemory(settings)
    level = memory.increment_friendship("t1", "u1", 0.5)
    assert level == 1.5
    assert memory.get_user_state("t1", "u1").friendship_level == 1.5

    memory2 = FriendMemory(settings)
    reloaded = memory2.get_user_state("t1", "u1")
    assert reloaded.friendship_level == 1.5
    assert reloaded.user_id == "u1"
    assert reloaded.tenant_id == "t1"


def test_friend_personality_interact_greet(tmp_path):
    settings = _settings(tmp_path)
    friend = FriendPersonality(settings)
    result = friend.interact(
        "greet",
        "t1",
        "u1",
        {"time_of_day": "morning"},
    )
    assert result["greeting"]
    assert "u1" in result["greeting"]
    assert result["state"]["greeting_count"] == 1


def test_friend_personality_build_rapport(tmp_path):
    settings = _settings(tmp_path)
    friend = FriendPersonality(settings)
    state = friend.build_rapport("t1", "u1")
    assert state.friendship_level > 1.0
    assert state.last_interaction


def test_friend_personality_get_response(tmp_path):
    settings = _settings(tmp_path)
    friend = FriendPersonality(settings)
    response = friend.get_response("u1", "t1", "Use the print function.")
    assert "Use the print function." in response
    assert "u1" in response


def test_feature_flag_disabled(tmp_path):
    settings = _settings(tmp_path)
    settings.enable_friend_personality = False
    friend = FriendPersonality(settings)
    result = friend.interact("greet", "t1", "u1", {"time_of_day": "morning"})
    assert result["enabled"] is False
    assert "disabled" in result["message"].lower()
    raw = friend.get_response("t1", "u1", "hello")
    assert raw == "hello"


def test_orchestrator_friend_directive_respects_flag():
    from ide_core.agent.config import AgentConfig
    from ide_core.agent.orchestrator import AgentOrchestrator

    settings = IDESettings()
    settings.enable_friend_personality = True
    agent = AgentOrchestrator(
        None, None, None, AgentConfig(), ide_settings=settings
    )
    prompt = agent._build_system_prompt()
    assert "warm" in prompt.lower() or "friendly" in prompt.lower()

    settings.enable_friend_personality = False
    agent2 = AgentOrchestrator(
        None, None, None, AgentConfig(), ide_settings=settings
    )
    prompt2 = agent2._build_system_prompt()
    assert "warm" not in prompt2.lower()
