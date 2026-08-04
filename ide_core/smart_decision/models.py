"""Core dataclasses for the smart decision subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DecisionOption:
    """A single candidate that can be evaluated and ranked."""

    option_id: str
    name: str
    description: str
    score: float = 0.0
    preview_url_or_path: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class DecisionContext:
    """Context used when scoring and choosing between options."""

    user_id: str
    tenant_id: str
    project_type: str = "general"
    creative_domain: Optional[str] = None
    history: list[dict] = field(default_factory=list)


@dataclass
class DecisionResult:
    """The outcome of a smart decision."""

    decision_id: str
    chosen_option: DecisionOption
    alternatives: list[DecisionOption]
    reason: str
    confidence: float
    explanation_level: str = "friendly"
