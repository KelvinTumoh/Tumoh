"""Celebration and encouragement messages for coding milestones."""

from __future__ import annotations

from .models import UserState


class Celebrator:
    """Generates enthusiastic celebrations and motivational encouragement."""

    _CELEBRATIONS = {
        "test_pass": [
            "All tests passed",
            "Green across the board",
            "Tests are shining",
        ],
        "build_success": [
            "Build succeeded",
            "Clean build",
            "Compiled like a dream",
        ],
        "streak": [
            "Streak milestone reached",
            "You're on fire",
            "What a run",
        ],
    }

    _EMOJIS = {
        "test_pass": "",
        "build_success": "",
        "streak": "",
    }

    _ENCOURAGEMENTS = {
        "test_failure": [
            "Test failure happens—let's debug it together",
            "Every failure is one step closer to green",
            "Let's debug this together",
        ],
        "terminal_error": [
            "That error is no match for you",
            "Bumps in the terminal happen",
            "Let's turn that red text into a win",
        ],
    }

    def celebrate(self, achievement_type: str, user_state: UserState) -> str:
        """Return an enthusiastic message with emojis for a milestone."""
        options = self._CELEBRATIONS.get(achievement_type, ["Great job"])
        emojis = self._EMOJIS.get(achievement_type, "")
        index = min(int(user_state.friendship_level) - 1, len(options) - 1)
        base = options[index % len(options)]
        return f"{base}, {user_state.user_id}! {emojis}".strip()

    def get_encouragement(self, situation: str, user_state: UserState) -> str:
        """Return a motivational phrase for a rough coding moment."""
        options = self._ENCOURAGEMENTS.get(
            situation, ["You've got this, keep going"]
        )
        index = min(int(user_state.friendship_level) - 1, len(options) - 1)
        base = options[index % len(options)]
        return f"{base}, {user_state.user_id}."
