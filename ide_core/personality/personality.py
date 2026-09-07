"""Main facade for the friend personality subsystem."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from ide_core.config.settings import IDESettings

from .celebrator import Celebrator
from .greeter import Greeter
from .helper import ProactiveHelper
from .memory import FriendMemory
from .models import UserState


class FriendPersonality:
    """Coordinates greeting, celebration, proactive help, and memory."""

    def __init__(
        self,
        settings: IDESettings | None = None,
        memory: FriendMemory | None = None,
        greeter: Greeter | None = None,
        celebrator: Celebrator | None = None,
        helper: ProactiveHelper | None = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._memory = memory or FriendMemory(self._settings)
        self._greeter = greeter or Greeter()
        self._celebrator = celebrator or Celebrator()
        self._helper = helper or ProactiveHelper()

    def interact(
        self, action: str, tenant_id: str, user_id: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        """Process an interaction and return a personalized response payload."""
        if not self._settings.enable_friend_personality:
            return {"enabled": False, "message": "Friend personality is disabled."}

        state = self._memory.get_user_state(tenant_id, user_id)

        if action == "greet":
            time_of_day = context.get(
                "time_of_day", self._greeter.infer_time_of_day()
            )
            state.greeting_count += 1
            if state.greeting_count > 1:
                greeting = self._greeter.get_welcome_back(state)
            else:
                greeting = self._greeter.get_greeting(time_of_day, state)
            self._update_state(state, tenant_id, user_id)
            return {"greeting": greeting, "state": asdict(state)}

        if action == "farewell":
            farewell = self._greeter.get_farewell(state)
            self._update_state(state, tenant_id, user_id)
            return {"farewell": farewell, "state": asdict(state)}

        if action == "celebrate":
            achievement = context.get("achievement_type", "milestone")
            state.achievements.append(achievement)
            celebration = self._celebrator.celebrate(achievement, state)
            self._update_state(state, tenant_id, user_id)
            return {"celebration": celebration, "state": asdict(state)}

        if action == "proactive":
            suggestion = self._helper.suggest_help(
                context.get("workflow_action", ""), context
            )
            self._update_state(state, tenant_id, user_id)
            return {"suggestion": suggestion, "state": asdict(state)}

        if action == "encourage":
            situation = context.get("situation", "test_failure")
            encouragement = self._celebrator.get_encouragement(situation, state)
            self._update_state(state, tenant_id, user_id)
            return {"encouragement": encouragement, "state": asdict(state)}

        prompt = context.get("prompt", "")
        # get_response is async; interact keeps the unadorned prompt when not awaited.
        return {"response": prompt, "state": asdict(state)}

    async def get_response(self, user_id: str, tenant_id: str, prompt: str) -> str:
        """Decorate a response with personality traits."""
        if not self._settings.enable_friend_personality or not prompt:
            return prompt

        state = self._memory.get_user_state(tenant_id, user_id)
        if state is None:
            if asyncio.iscoroutinefunction(self._memory.get_user_state):
                state = await self._memory.get_user_state(tenant_id, user_id)
            else:
                state = self._memory.get_user_state(tenant_id, user_id)

        time_of_day = self._greeter.infer_time_of_day()
        greeting = self._greeter.get_greeting(time_of_day, state)
        return f"{greeting} {prompt}"

    def build_rapport(self, tenant_id: str, user_id: str) -> UserState:
        """Increment friendship and update the user's last interaction."""
        state = self._memory.get_user_state(tenant_id, user_id)
        if self._settings.enable_friend_personality:
            state.friendship_level = min(
                10.0, state.friendship_level + 0.1
            )
            state.last_interaction = _now_iso()
            self._memory._save_user_state(tenant_id, user_id, state)
        return state

    def _update_state(self, state: UserState, tenant_id: str, user_id: str) -> None:
        state.last_interaction = _now_iso()
        self._memory._save_user_state(tenant_id, user_id, state)

    @staticmethod
    def get_system_directive() -> str:
        """Return a lightweight system directive for agent prompts."""
        return (
            "Maintain a warm, friendly, and encouraging tone in your final "
            "responses, while keeping tool calls and code modifications "
            "precise and accurate."
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
