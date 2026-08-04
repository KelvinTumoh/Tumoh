"""Persistent, tenant-isolated preference learning for smart decisions."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from ide_core.config.settings import IDESettings

from .models import DecisionOption


class DecisionLearner:
    """Learn from user feedback and persist per-tenant, per-user preferences."""

    def __init__(self, settings: Optional[IDESettings] = None) -> None:
        self._settings = settings or IDESettings()
        self._root = Path(self._settings.preference_storage_path)

    def _user_path(self, tenant_id: str, user_id: str) -> Path:
        return self._root / tenant_id / f"{user_id}.json"

    def _ensure_dirs(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def _default_preferences(self) -> dict[str, Any]:
        return {
            "weights": {
                "preference": 0.4,
                "quality": 0.3,
                "speed": 0.2,
                "style": 0.1,
            },
            "style_preferences": {},
            "media_preferences": {},
            "history": [],
            "decisions": {},
            "feedback": [],
        }

    def _load(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return self._default_preferences()
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return self._default_preferences()

    def _save(self, path: Path, data: dict[str, Any]) -> None:
        self._ensure_dirs(path)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _normalize_weights(self, data: dict[str, Any]) -> None:
        weights = data.get("weights", {})
        total = sum(
            float(v) for v in weights.values() if isinstance(v, (int, float))
        )
        if total <= 0:
            total = 1.0
        data["weights"] = {
            k: round(float(v) / total, 4)
            for k, v in weights.items()
            if isinstance(v, (int, float))
        }

    async def get_user_preferences(
        self, tenant_id: str, user_id: str
    ) -> dict[str, Any]:
        """Return the stored preferences for a tenant+user pair."""
        path = self._user_path(tenant_id, user_id)
        return self._load(path)

    async def record_decision(
        self,
        tenant_id: str,
        user_id: str,
        decision_id: str,
        chosen_option: DecisionOption,
        alternatives: list[DecisionOption],
    ) -> None:
        """Store a decision record so feedback can reference it later."""
        prefs = await self.get_user_preferences(tenant_id, user_id)
        prefs["decisions"][decision_id] = {
            "chosen_option": asdict(chosen_option),
            "alternatives": [asdict(a) for a in alternatives],
        }
        path = self._user_path(tenant_id, user_id)
        self._save(path, prefs)

    async def learn_from_feedback(
        self,
        tenant_id: str,
        user_id: str,
        decision_id: str,
        selected_option_id: str,
        rating: float,
        comments: Optional[str] = None,
    ) -> dict[str, float]:
        """Update preference weights based on user feedback."""
        prefs = await self.get_user_preferences(tenant_id, user_id)
        decision = prefs.get("decisions", {}).get(decision_id, {})
        chosen = decision.get("chosen_option", {}) or {}

        style = (
            chosen.get("metadata", {}).get("style")
            if chosen
            else selected_option_id
        )
        media = chosen.get("metadata", {}).get("media") if chosen else None
        option_id = chosen.get("option_id") if chosen else selected_option_id

        # Normalize a 1-5 rating to [-1.0, 1.0]
        normalized = (float(rating) - 3.0) / 2.0
        normalized = max(-1.0, min(1.0, normalized))

        # Reinforce/dampen style/media preferences
        for key in (style, media, option_id):
            if not key:
                continue
            current = prefs["style_preferences"].get(key, 0.5)
            delta = normalized * 0.1
            prefs["style_preferences"][key] = max(
                0.0, min(1.0, round(current + delta, 4))
            )

        # Slightly nudge global factor weights
        for factor in ("preference", "quality", "speed", "style"):
            current = prefs["weights"].get(factor, 0.25)
            delta = normalized * 0.02
            prefs["weights"][factor] = max(0.0, min(1.0, round(current + delta, 4)))

        self._normalize_weights(prefs)

        prefs["feedback"].append(
            {
                "decision_id": decision_id,
                "selected_option_id": selected_option_id,
                "rating": rating,
                "comments": comments,
            }
        )

        if chosen:
            prefs["history"].append(
                {
                    "decision_id": decision_id,
                    "chosen_option_id": option_id,
                    "style": style,
                    "media": media,
                }
            )

        path = self._user_path(tenant_id, user_id)
        self._save(path, prefs)
        return prefs["weights"]
