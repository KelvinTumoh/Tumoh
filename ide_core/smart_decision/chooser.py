"""High-level chooser that ranks options and produces a decision result."""

from __future__ import annotations

import uuid
from typing import Optional

from ide_core.config.settings import IDESettings

from .models import DecisionContext, DecisionOption, DecisionResult
from .scorer import OptionScorer


class SmartChooser:
    """Score, sort, and select the best candidate option."""

    def __init__(
        self,
        scorer: Optional[OptionScorer] = None,
        settings: Optional[IDESettings] = None,
    ) -> None:
        self._scorer = scorer or OptionScorer()
        self._settings = settings or IDESettings()

    async def choose_best(
        self,
        options: list[DecisionOption],
        context: DecisionContext,
    ) -> DecisionResult:
        """Score all options and return the top choice plus alternatives."""
        if not options:
            raise ValueError("At least one option is required to make a decision.")

        scored = [
            (self._scorer.score_option(option, context), option) for option in options
        ]
        scored.sort(key=lambda x: x[0], reverse=True)

        chosen = scored[0][1]
        alternatives = [option for _, option in scored[1:]]

        total = sum(option.score for option in options)
        confidence = round(chosen.score / total, 4) if total > 0 else 0.0

        level = getattr(self._settings, "decision_explain_level", "friendly")
        reason = self._format_reason(chosen, alternatives, context, level)

        return DecisionResult(
            decision_id=uuid.uuid4().hex,
            chosen_option=chosen,
            alternatives=alternatives,
            reason=reason,
            confidence=confidence,
            explanation_level=level,
        )

    def _format_reason(
        self,
        chosen: DecisionOption,
        alternatives: list[DecisionOption],
        context: DecisionContext,
        level: str,
    ) -> str:
        if level == "minimal":
            return f"Chose {chosen.name}."

        if level == "detailed":
            alt_names = ", ".join(o.name for o in alternatives[:3]) or "none"
            return (
                f"Selected {chosen.name} (score {chosen.score:.2f}) for your "
                f"{context.project_type} project in the "
                f"{context.creative_domain or 'general'} domain. "
                f"Alternatives considered: {alt_names}."
            )

        return f"I picked {chosen.name} because it scored highest for this project."
