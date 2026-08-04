"""Map natural-language or multimodal text into a structured creative request."""

from __future__ import annotations

import re
import uuid
from typing import Any, Optional, Union

from .models import CreativeDomain, CreativeRequest


class CreativeIntentEngine:
    """Interpret creative intent and extract style/format parameters."""

    def __init__(self) -> None:
        self._style_keywords = (
            "minimal",
            "pixel",
            "cartoon",
            "realistic",
            "flat",
            "3d",
            "neon",
            "watercolor",
            "sketch",
            "modern",
            "vintage",
            "monochrome",
            "colorful",
        )

    async def interpret(
        self, text_or_processed_input: Union[str, Any]
    ) -> CreativeRequest:
        """Async wrapper around the synchronous interpretation logic."""
        return self.interpret_text(text_or_processed_input)

    def interpret_text(
        self, text_or_processed_input: Union[str, Any]
    ) -> CreativeRequest:
        """Turn raw text or a processed input into a creative request."""
        if hasattr(text_or_processed_input, "raw_text"):
            text = text_or_processed_input.raw_text
            tenant_id = getattr(text_or_processed_input, "tenant_id", None)
        else:
            text = text_or_processed_input
            tenant_id = None

        text = (text or "").strip()
        domain = self._detect_domain(text)
        style = self._extract_style(text)
        options = self._extract_options(text)

        return CreativeRequest(
            request_id=uuid.uuid4().hex,
            domain=domain,
            prompt=text,
            style=style,
            options=options,
            tenant_id=tenant_id,
        )

    def _detect_domain(self, text: str) -> CreativeDomain:
        t = text.lower()

        if any(w in t for w in ("logo", "brand mark", "emblem", "brand icon")):
            return CreativeDomain.LOGO

        if any(
            w in t
            for w in ("ui mockup", "mockup", "wireframe", "screen design", "web page")
        ):
            return CreativeDomain.UI_MOCKUP

        if any(w in t for w in ("game asset", "sprite", "tileset", "texture")):
            return CreativeDomain.GAME_ASSET

        if any(w in t for w in ("voice", "narration", "tts", "voiceover")):
            return CreativeDomain.VOICEOVER

        if any(
            w in t
            for w in ("background music", "soundtrack", "music track", "bgm")
        ):
            return CreativeDomain.SOUND

        if any(w in t for w in ("sound", "sfx", "audio effect", "jingle")):
            return CreativeDomain.SOUND

        if any(
            w in t
            for w in ("video", "demo", "tutorial", "walkthrough", "screen recording")
        ):
            return CreativeDomain.VIDEO

        if any(
            w in t
            for w in ("image", "picture", "graphic", "illustration", "photo", "draw")
        ):
            return CreativeDomain.IMAGE

        # Default to a generic image when a creative keyword is present.
        return CreativeDomain.IMAGE

    def _extract_style(self, text: str) -> Optional[str]:
        t = text.lower()
        for style in self._style_keywords:
            if style in t:
                return style
        return None

    def _extract_options(self, text: str) -> dict:
        options: dict = {}
        for match in re.finditer(r"(\w+):\s*([^\s,]+)", text):
            key = match.group(1).lower()
            raw_value = match.group(2)
            if raw_value.isdigit():
                value: Union[int, str] = int(raw_value)
            else:
                value = raw_value
            options[key] = value
        return options
