"""Deterministic, mock-friendly option scoring."""

from __future__ import annotations

from .models import DecisionContext, DecisionOption


class OptionScorer:
    """Score a candidate option across multiple weighted factors."""

    default_weights = {
        "preference": 0.4,
        "quality": 0.3,
        "speed": 0.2,
        "style": 0.1,
    }

    def __init__(self, factor_weights: dict | None = None) -> None:
        self.factor_weights = factor_weights or self.default_weights.copy()

    def score_option(
        self,
        option: DecisionOption,
        context: DecisionContext,
        learned_weights: dict | None = None,
    ) -> float:
        """Return a normalized 0.0-1.0 score for ``option``."""
        weights = learned_weights if learned_weights is not None else self.factor_weights
        if not weights or not isinstance(weights, dict):
            weights = self.default_weights.copy()

        total = sum(
            float(v) for v in weights.values() if isinstance(v, (int, float))
        )
        if total <= 0:
            total = 1.0
        normalized = {
            k: float(v) / total
            for k, v in weights.items()
            if isinstance(v, (int, float))
        }

        qf = self._quality_fit(option)
        se = self._speed_estimate(option)
        hm = self._historical_preference_match(option, context)
        ps = self._project_style_alignment(option, context)

        score = (
            normalized.get("quality", 0.0) * qf
            + normalized.get("speed", 0.0) * se
            + normalized.get("preference", 0.0) * hm
            + normalized.get("style", 0.0) * ps
        )
        score = max(0.0, min(1.0, round(score, 6)))
        option.score = score
        return score

    @staticmethod
    def _to_float(value: object, default: float = 0.5) -> float:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    def _quality_fit(self, option: DecisionOption) -> float:
        q = option.metadata.get("quality", 0.5)
        return max(0.0, min(1.0, self._to_float(q, 0.5)))

    def _speed_estimate(self, option: DecisionOption) -> float:
        s = option.metadata.get("speed", 0.5)
        return max(0.0, min(1.0, self._to_float(s, 0.5)))

    def _historical_preference_match(
        self, option: DecisionOption, context: DecisionContext
    ) -> float:
        if not context.history:
            return 0.5

        style = option.metadata.get("style")
        option_id = option.option_id
        matches = 0
        for entry in context.history:
            if entry.get("chosen_option_id") == option_id:
                matches += 2
            elif style and entry.get("style") == style:
                matches += 1

        return min(1.0, matches / max(1, len(context.history)))

    def _project_style_alignment(
        self, option: DecisionOption, context: DecisionContext
    ) -> float:
        score = 0.3
        pt = context.project_type or "general"
        cd = context.creative_domain
        style = option.metadata.get("style")
        domain = option.metadata.get("domain")
        tags = option.metadata.get("tags", [])

        if style and (style == pt or style == cd or style in tags):
            score += 0.3
        if cd and domain == cd:
            score += 0.3
        if pt != "general" and pt in tags:
            score += 0.1

        return max(0.0, min(1.0, score))
