"""Creative agent dataclasses and enums."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CreativeDomain(Enum):
    """Categories of creative output the agent can produce."""

    IMAGE = "image"
    SOUND = "sound"
    VIDEO = "video"
    LOGO = "logo"
    UI_MOCKUP = "ui_mockup"
    GAME_ASSET = "game_asset"
    VOICEOVER = "voiceover"


@dataclass
class CreativeTool:
    """Description of an external tool the creative agent may require."""

    name: str
    domain: CreativeDomain
    description: str
    install_command: str
    is_installed: bool = False


@dataclass
class CreativeRequest:
    """A normalized creative generation request."""

    request_id: str
    domain: CreativeDomain
    prompt: str
    style: str | None = None
    options: dict = field(default_factory=dict)
    tenant_id: str | None = None


@dataclass
class CreativeResult:
    """The artifact produced by a creative generator."""

    request_id: str
    success: bool
    domain: CreativeDomain
    output_path: str | None = None
    preview_data: bytes | None = None
    metadata: dict = field(default_factory=dict)
    message: str = ""
