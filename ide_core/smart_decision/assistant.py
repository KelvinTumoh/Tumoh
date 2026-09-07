"""High-level coordinator for the smart decision subsystem."""

from __future__ import annotations

import uuid

from ide_core.config.settings import IDESettings
from ide_core.logging.logger import IDELogger

from .chooser import SmartChooser
from .learner import DecisionLearner
from .models import DecisionContext, DecisionOption, DecisionResult
from .scorer import OptionScorer


class SmartAssistant:
    """Coordinate learning, scoring, and choosing for smart decisions."""

    def __init__(
        self,
        settings: IDESettings | None = None,
        logger: IDELogger | None = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._logger = logger or IDELogger(self._settings)
        self._learner = DecisionLearner(self._settings)
        self._scorer = OptionScorer()
        self._chooser = SmartChooser(self._scorer, self._settings)

    async def decide(
        self,
        options: list[DecisionOption],
        context: DecisionContext,
    ) -> DecisionResult:
        """Score, choose, and optionally record a smart decision."""
        if not self._settings.enable_smart_decisions:
            chosen = options[0]
            return DecisionResult(
                decision_id=uuid.uuid4().hex,
                chosen_option=chosen,
                alternatives=options[1:],
                reason="Smart decisions are disabled; using first candidate.",
                confidence=1.0,
                explanation_level=getattr(
                    self._settings, "decision_explain_level", "friendly"
                ),
            )

        learned = await self._learner.get_user_preferences(
            context.tenant_id, context.user_id
        )
        self._scorer.factor_weights = learned.get(
            "weights", OptionScorer.default_weights.copy()
        )

        result = await self._chooser.choose_best(options, context)

        if self._settings.auto_learn_from_feedback:
            await self._learner.record_decision(
                context.tenant_id,
                context.user_id,
                result.decision_id,
                result.chosen_option,
                result.alternatives,
            )

        return result

    def explain_decision(self, result: DecisionResult) -> str:
        """Return a human-readable explanation for a decision."""
        level = result.explanation_level
        if level == "minimal":
            return f"Choice: {result.chosen_option.name}."

        if level == "detailed":
            alt = ", ".join(o.name for o in result.alternatives[:3]) or "none"
            return (
                f"Chose {result.chosen_option.name} with confidence "
                f"{result.confidence:.2%}. {result.reason} "
                f"Other options: {alt}."
            )

        return f"I chose {result.chosen_option.name} for this task."

    def get_alternatives(self, result: DecisionResult) -> list[DecisionOption]:
        """Return the non-selected alternatives from a decision."""
        return result.alternatives
