"""Shared dataclasses and enums for multimodal input processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class InputType(Enum):
    """Supported categories of multimodal input."""

    VOICE = "voice"
    TEXT = "text"
    IMAGE = "image"
    PDF = "pdf"
    DOCUMENT = "document"
    SCREENSHOT = "screenshot"
    AUTO = "auto"


@dataclass
class MultimodalInput:
    """A raw multimodal payload submitted to the engine."""

    input_id: str
    input_type: InputType
    content: bytes
    metadata: dict = field(default_factory=dict)
    source: str = ""
    tenant_id: str | None = None


@dataclass
class ProcessedInput:
    """Structured output produced by the multimodal input engine."""

    input_id: str
    raw_text: str
    intent: str = ""
    entities: list[str] = field(default_factory=list)
    summary: str = ""
    extracted_assets: dict = field(default_factory=dict)
