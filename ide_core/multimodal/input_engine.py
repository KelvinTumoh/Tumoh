"""Router that orchestrates all multimodal processors."""

from __future__ import annotations

import json
import re
from typing import Optional

from ide_core.config.settings import IDESettings
from ide_core.logging.logger import IDELogger

from .document_processor import DocumentProcessor
from .image_processor import ImageProcessor
from .models import InputType, MultimodalInput, ProcessedInput
from .pdf_processor import PDFProcessor
from .utils import detect_mime_type
from .voice_processor import VoiceProcessor

from ide_core.creative.intent_engine import CreativeIntentEngine


class MultimodalInputEngine:
    """Transform raw multimodal payloads into structured agent-ready context."""

    def __init__(
        self,
        settings: Optional[IDESettings] = None,
        logger: Optional[IDELogger] = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._logger = logger or IDELogger(self._settings)
        self._voice = VoiceProcessor(self._settings, self._logger)
        self._image = ImageProcessor(self._settings, self._logger)
        self._pdf = PDFProcessor(self._settings, self._logger)
        self._document = DocumentProcessor(self._settings, self._logger)

    async def process_input(self, input_data: MultimodalInput) -> ProcessedInput:
        """Route and process a multimodal payload, respecting feature flags."""
        if not self._settings.enable_multimodal:
            return self._disabled_result(input_data, "multimodal engine disabled")

        input_type = input_data.input_type
        if input_type == InputType.AUTO:
            input_type = detect_mime_type(input_data.content)

        try:
            raw_text = await self._route(input_data, input_type)
        except Exception as exc:
            self._logger.log_event(
                "multimodal_processing_error",
                input_id=input_data.input_id,
                error=str(exc),
            )
            raw_text = f"[Multimodal processing error: {exc}]"

        return ProcessedInput(
            input_id=input_data.input_id,
            raw_text=raw_text,
            intent=self._infer_intent(raw_text),
            entities=self._extract_entities(raw_text),
            summary=self._summarize(raw_text),
            extracted_assets=self._build_assets(input_data, input_type),
        )

    async def _route(self, input_data: MultimodalInput, input_type: InputType) -> str:
        if input_type == InputType.VOICE:
            return await self._voice.transcribe(
                input_data.content,
                language=self._settings.voice_language,
            )

        if input_type in (InputType.IMAGE, InputType.SCREENSHOT):
            return self._image.extract_text(input_data.content)

        if input_type == InputType.PDF:
            return self._pdf.extract_text(input_data.content)

        if input_type == InputType.DOCUMENT:
            ext = input_data.metadata.get("file_extension") or input_data.metadata.get(
                "extension", "txt"
            )
            return self._document.extract_text(input_data.content, ext)

        # TEXT and unknown inputs
        try:
            return input_data.content.decode("utf-8")
        except UnicodeDecodeError:
            return input_data.content.decode("utf-8", errors="ignore")

    def _infer_intent(self, text: str) -> str:
        t = text.lower()
        if any(w in t for w in ("create", "generate", "write", "implement", "add")):
            return "create"
        if any(w in t for w in ("fix", "error", "bug", "debug", "resolve")):
            return "fix"
        if any(w in t for w in ("explain", "what", "how", "describe", "clarify")):
            return "explain"
        if any(w in t for w in ("refactor", "rename", "restructure", "simplify")):
            return "refactor"
        return "general"

    def _extract_entities(self, text: str) -> list[str]:
        found: set[str] = set()
        for match in re.findall(r'"([^"]+)"', text):
            found.add(match)
        for match in re.findall(r"`([^`]+)`", text):
            found.add(match)
        for match in re.findall(
            r"\b[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+\.[A-Za-z]{2,}\b",
            text,
        ):
            found.add(match)
        for match in re.findall(
            r"\b(?:[a-zA-Z]:\\|/|\\)?(?:[\w-]+[/\\])*[\w-]+\.[a-zA-Z0-9]+\b",
            text,
        ):
            found.add(match)
        return list(found)

    def _summarize(self, text: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        if sentences and sentences[0].strip():
            return sentences[0].strip()[:240]
        return text[:240].strip()

    def _build_assets(self, input_data: MultimodalInput, input_type: InputType) -> dict:
        assets: dict = {}
        if input_type == InputType.PDF:
            assets["images"] = len(self._pdf.extract_images(input_data.content))
        return assets

    def _disabled_result(
        self, input_data: MultimodalInput, reason: str
    ) -> ProcessedInput:
        self._logger.log_event(
            "multimodal_disabled",
            input_id=input_data.input_id,
            reason=reason,
        )
        msg = f"[Multimodal input disabled: {reason}]"
        return ProcessedInput(
            input_id=input_data.input_id,
            raw_text=msg,
            intent="none",
            entities=[],
            summary=msg,
            extracted_assets={},
        )

    def to_agent_context(self, processed: ProcessedInput) -> str:
        """Format a processed input as markdown context for an agent prompt."""
        lines = [
            f"## Multimodal Input: {processed.input_id}",
            "",
            f"**Intent:** {processed.intent}",
            "",
            "**Raw Text:**",
            processed.raw_text,
            "",
            "**Entities:**",
            "\n".join(f"- {entity}" for entity in processed.entities) or "-",
            "",
            f"**Summary:** {processed.summary}",
            "",
            "**Extracted Assets:**",
            json.dumps(processed.extracted_assets, indent=2, default=str),
        ]
        context = "\n".join(lines)

        if self._settings.enable_creative_agent and self._looks_creative(
            processed.raw_text
        ):
            engine = CreativeIntentEngine()
            request = engine.interpret_text(processed.raw_text)
            creative_block = [
                "",
                "### Creative Intent Hint",
                f"- **Domain:** {request.domain.value}",
                f"- **Prompt:** {request.prompt}",
                f"- **Style:** {request.style or 'unspecified'}",
                f"- **Options:** {json.dumps(request.options, default=str)}",
            ]
            context += "\n".join(creative_block)

        return context

    def _looks_creative(self, text: str) -> bool:
        creative_keywords = (
            "logo",
            "image",
            "graphic",
            "mockup",
            "ui",
            "sound",
            "music",
            "voice",
            "video",
            "tutorial",
            "demo",
            "draw",
            "illustration",
        )
        t = text.lower()
        return any(k in t for k in creative_keywords)
