"""Main creative agent controller."""

from __future__ import annotations

from ide_core.config.settings import IDESettings
from ide_core.logging.logger import IDELogger
from ide_core.smart_decision.assistant import SmartAssistant
from ide_core.smart_decision.models import DecisionContext, DecisionOption

from .generators.image_gen import ImageGenerator
from .generators.sound_gen import SoundGenerator
from .generators.video_gen import VideoGenerator
from .intent_engine import CreativeIntentEngine
from .models import CreativeDomain, CreativeRequest, CreativeResult
from .tool_installer import ToolInstaller


class CreativeAgent:
    """Orchestrate creative intent, tool installation, and artifact generation."""

    def __init__(
        self,
        settings: IDESettings | None = None,
        logger: IDELogger | None = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._logger = logger or IDELogger(self._settings)

        if not self._settings.enable_creative_agent:
            return

        self._intent = CreativeIntentEngine()
        self._installer = ToolInstaller(self._settings, self._logger)
        self._image = ImageGenerator(self._settings, self._logger)
        self._sound = SoundGenerator(self._settings, self._logger)
        self._video = VideoGenerator(self._settings, self._logger)

    async def execute(self, request: CreativeRequest) -> CreativeResult:
        """Run the full creative workflow and return a workspace artifact."""
        if not self._settings.enable_creative_agent:
            return CreativeResult(
                request_id=request.request_id,
                success=False,
                domain=request.domain,
                message="Creative agent disabled",
            )

        self._logger.log_event(
            "creative_execute_started",
            request_id=request.request_id,
            domain=request.domain.value,
        )

        if self._settings.enable_smart_decisions and request.options.get(
            "candidates"
        ):
            return await self._decide_candidates(request)

        if request.domain == CreativeDomain.VIDEO:
            await self._installer.ensure_tool("ffmpeg")

        if request.domain in (
            CreativeDomain.IMAGE,
            CreativeDomain.LOGO,
            CreativeDomain.UI_MOCKUP,
            CreativeDomain.GAME_ASSET,
        ):
            if request.domain == CreativeDomain.LOGO:
                return await self._image.generate_logo(
                    request.prompt, request.style or "minimal"
                )
            if request.domain == CreativeDomain.UI_MOCKUP:
                return await self._image.generate_ui_mockup(request.prompt)
            return await self._image.generate(
                request.prompt, request.style or "default"
            )

        if request.domain in (CreativeDomain.SOUND, CreativeDomain.VOICEOVER):
            if request.domain == CreativeDomain.VOICEOVER:
                return await self._sound.generate_voiceover(
                    request.prompt,
                    request.options.get("voice", "alloy"),
                )
            if request.options.get("type") == "music" or "music" in request.prompt.lower():
                duration = int(request.options.get("duration", 10))
                return await self._sound.generate_music(
                    request.style or "neutral", duration
                )
            return await self._sound.generate_sound(request.prompt)

        if request.domain == CreativeDomain.VIDEO:
            if request.options.get("kind") == "tutorial":
                return await self._video.generate_tutorial(
                    request.options.get("steps", [])
                )
            return await self._video.generate_demo(
                request.prompt,
                request.options.get("features", []),
            )

        return CreativeResult(
            request_id=request.request_id,
            success=False,
            domain=request.domain,
            message="Unsupported creative domain",
        )

    async def _decide_candidates(self, request: CreativeRequest) -> CreativeResult:
        """Route a list of pre-generated candidates through SmartAssistant."""
        options = []
        for c in request.options.get("candidates", []):
            options.append(
                DecisionOption(
                    option_id=c["option_id"],
                    name=c["name"],
                    description=c.get("description", ""),
                    preview_url_or_path=c.get("preview_url_or_path"),
                    metadata=c.get("metadata", {}),
                )
            )

        context = DecisionContext(
            user_id=request.options.get("user_id", "anonymous"),
            tenant_id=request.tenant_id or "default",
            project_type=request.options.get("project_type", "general"),
            creative_domain=request.domain.value,
            history=request.options.get("history", []),
        )

        assistant = SmartAssistant(self._settings, self._logger)
        result = await assistant.decide(options, context)

        return CreativeResult(
            request_id=request.request_id,
            success=True,
            domain=request.domain,
            output_path=result.chosen_option.preview_url_or_path,
            message=result.reason,
            metadata={
                "smart_decision_id": result.decision_id,
                "smart_reason": result.reason,
                "smart_confidence": result.confidence,
                "smart_alternatives": [
                    {
                        "option_id": a.option_id,
                        "name": a.name,
                        "score": a.score,
                        "preview_url_or_path": a.preview_url_or_path,
                    }
                    for a in result.alternatives
                ],
                "chosen_option_score": result.chosen_option.score,
                **result.chosen_option.metadata,
            },
        )
