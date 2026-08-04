"""Time-aware, friendship-scaled greeting and farewell generation."""

from __future__ import annotations

from datetime import datetime

from .models import UserState


class Greeter:
    """Generates warm, contextual greetings, farewells, and welcome-backs."""

    _TIME_LABELS = {
        "morning": (5, 12),
        "afternoon": (12, 18),
        "evening": (18, 22),
    }

    _GREETINGS = {
        "morning": [
            "Good morning",
            "Rise and shine",
            "Top of the morning",
        ],
        "afternoon": [
            "Good afternoon",
            "Hope your day is going well",
            "Hello there",
        ],
        "evening": [
            "Good evening",
            "Nice to see you this evening",
            "Evening",
        ],
        "night": [
            "Working late",
            "Good night",
            "Still up coding",
        ],
    }

    _FAREWELLS = [
        "Catch you later",
        "Happy coding",
        "See you next time",
        "Take care",
    ]

    _WELCOME_BACKS = [
        "Welcome back",
        "Great to see you again",
        "Back at it",
        "Picked up where you left off",
    ]

    @classmethod
    def infer_time_of_day(cls) -> str:
        """Map the current hour to a friendly time-of-day label."""
        hour = datetime.now().hour
        for label, (start, end) in cls._TIME_LABELS.items():
            if start <= hour < end:
                return label
        return "night"

    def get_greeting(self, time_of_day: str, user_state: UserState) -> str:
        """Return a time-appropriate, friendship-scaled greeting."""
        options = self._GREETINGS.get(time_of_day, self._GREETINGS["morning"])
        index = min(int(user_state.friendship_level) - 1, len(options) - 1)
        salutation = options[index % len(options)]
        return f"{salutation}, {user_state.user_id}!"

    def get_farewell(self, user_state: UserState) -> str:
        """Return a warm goodbye message."""
        index = min(int(user_state.friendship_level) - 1, len(self._FAREWELLS) - 1)
        base = self._FAREWELLS[index % len(self._FAREWELLS)]
        return f"{base}, {user_state.user_id}!"

    def get_welcome_back(self, user_state: UserState) -> str:
        """Return a personalized message for a returning user."""
        index = min(
            int(user_state.friendship_level) - 1, len(self._WELCOME_BACKS) - 1
        )
        base = self._WELCOME_BACKS[index % len(self._WELCOME_BACKS)]
        if user_state.last_interaction:
            return f"{base}, {user_state.user_id}! Your last session was {user_state.last_interaction}."
        return f"{base}, {user_state.user_id}!"
