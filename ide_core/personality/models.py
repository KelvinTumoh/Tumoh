"""Core data models for the friend personality subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Mood(Enum):
    """Possible emotional tones the companion can adopt."""

    CHEERFUL = "cheerful"
    ENCOURAGING = "encouraging"
    HELPFUL = "helpful"
    SILLY = "silly"
    EMPATHETIC = "empathetic"


@dataclass
class PersonalityTrait:
    """A named personality dimension with a 0.0-1.0 value."""

    name: str
    value: float = 0.5

    def __post_init__(self) -> None:
        self.value = max(0.0, min(1.0, float(self.value)))


@dataclass
class UserState:
    """Persistent, tenant-isolated state for a single user."""

    user_id: str
    tenant_id: str
    greeting_count: int = 0
    friendship_level: float = 1.0
    last_interaction: str = ""
    achievements: list[str] = field(default_factory=list)
    preferences: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.friendship_level = max(1.0, min(10.0, float(self.friendship_level)))
