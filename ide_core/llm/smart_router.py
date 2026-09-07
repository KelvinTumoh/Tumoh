"""Smart routing between DeepSeek V4 Pro and Gemini 1.5 Pro."""

from __future__ import annotations

from enum import Enum

from ide_core.config.settings import IDESettings


class ModelType(str, Enum):
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"


class SmartRouter:
    """Routes user inputs to the best LLM based on content and attachments."""

    # Attachments and user-agent use cases that require Gemini's multimodal support.
    _GEMINI_ATTACHMENT_TYPES = {
        "image",
        "images",
        "photo",
        "picture",
        "png",
        "jpg",
        "jpeg",
        "webp",
        "gif",
        "audio",
        "voice",
        "mp3",
        "wav",
        "pdf",
        "application/pdf",
    }

    _GEMINI_KEYWORDS = [
        # images
        "image",
        "images",
        "photo",
        "picture",
        "screenshot",
        "visual",
        # voice
        "voice",
        "speech",
        "audio",
        "listen",
        "say",
        # documents
        "pdf",
        "document",
        "upload",
        "scan",
        "ocr",
        # design
        "sketch",
        "mockup",
        "wireframe",
        "design",
        "ui",
        "logo",
        "drawing",
        "illustration",
        "blueprint",
        "floor plan",
        # video
        "video",
        "gif",
        "animation",
        "clip",
        # other multimodal
        "diagram",
        "chart",
        "graph",
        "recording",
        "multimodal",
    ]

    _DEEPSEEK_KEYWORDS = [
        # code
        "code",
        "coding",
        "program",
        "programming",
        "function",
        "class",
        "python",
        "javascript",
        "typescript",
        "react",
        "vue",
        "node",
        "django",
        "sql",
        # edits
        "edit",
        "change",
        "modify",
        "refactor",
        "fix",
        "bug",
        # planning
        "plan",
        "planning",
        "architecture",
        "structure",
        "database",
        "api",
        "endpoint",
        # logic
        "algorithm",
        "logic",
        "reasoning",
        "sort",
        "search",
        "optimize",
        "performance",
        # debugging
        "debug",
        "trace",
        "error",
        "exception",
        "crash",
        # general implementation
        "implement",
        "script",
        "write",
        "uml",
        "math",
        "equation",
        "proof",
    ]

    def __init__(self, settings: IDESettings | None = None):
        self.settings = settings or IDESettings()

    @staticmethod
    def _model_from_name(name: str) -> ModelType:
        name = name.lower().strip()
        if name == ModelType.GEMINI.value:
            return ModelType.GEMINI
        return ModelType.DEEPSEEK

    def _default_model(self) -> ModelType:
        return self._model_from_name(self.settings.routing_default_model)

    def _attachment_suggests_gemini(self, attachment_type: str | None) -> bool:
        if not attachment_type:
            return False
        lowered = attachment_type.lower().strip()
        if lowered in self._GEMINI_ATTACHMENT_TYPES:
            return True
        if lowered.startswith(("image/", "audio/", "video/")):
            return True
        return any(mime in lowered for mime in ("pdf", "image", "audio", "voice"))

    def _score_keywords(self, text: str, keywords: list[str]) -> int:
        lowered = text.lower()
        return sum(1 for keyword in keywords if keyword in lowered)

    def _analyze(
        self,
        user_input: str,
        has_attachments: bool = False,
        attachment_type: str | None = None,
    ) -> tuple[ModelType, str]:
        if not self.settings.enable_smart_routing:
            default = self._default_model()
            return default, f"Smart routing is disabled; defaulting to {default.value}."

        if has_attachments and self._attachment_suggests_gemini(attachment_type):
            return (
                ModelType.GEMINI,
                f"Routed to Gemini because the attachment type '{attachment_type}' "
                "requires multimodal understanding (image, voice, or PDF).",
            )

        gemini_score = self._score_keywords(user_input, self._GEMINI_KEYWORDS)
        deepseek_score = self._score_keywords(user_input, self._DEEPSEEK_KEYWORDS)

        if gemini_score and gemini_score >= deepseek_score:
            return (
                ModelType.GEMINI,
                "Routed to Gemini 1.5 Pro because the request involves images, "
                "design, audio, voice, or PDF content.",
            )

        if deepseek_score:
            return (
                ModelType.DEEPSEEK,
                "Routed to DeepSeek V4 Pro because the request involves coding, "
                "editing, planning, logic, or algorithmic reasoning.",
            )

        default = self._default_model()
        return (
            default,
            f"Routed to {default.value} (default) because no strong "
            "multimodal or code pattern was detected.",
        )

    def route(
        self,
        user_input: str,
        has_attachments: bool = False,
        attachment_type: str | None = None,
    ) -> ModelType:
        """Return the model best suited for the input."""
        model, _ = self._analyze(user_input, has_attachments, attachment_type)

        if model == ModelType.DEEPSEEK and not self.settings.enable_deepseek:
            if self.settings.enable_gemini:
                return ModelType.GEMINI
            return model

        if model == ModelType.GEMINI and not self.settings.enable_gemini:
            if self.settings.enable_deepseek:
                return ModelType.DEEPSEEK
            return model

        return model

    def get_routing_reason(
        self,
        user_input: str,
        selected_model: ModelType,
    ) -> str:
        """Return a human-readable explanation for the routing decision."""
        if not self.settings.enable_smart_routing:
            return (
                f"Smart routing is disabled; using the default model "
                f"{selected_model.value}."
            )

        if selected_model == ModelType.GEMINI:
            if self._score_keywords(user_input, self._GEMINI_KEYWORDS):
                return (
                    "Selected Gemini 1.5 Pro because the request references "
                    "images, design, audio, voice, or PDF content."
                )
            return (
                "Selected Gemini 1.5 Pro for its multimodal "
                "understanding capabilities."
            )

        if selected_model == ModelType.DEEPSEEK:
            if self._score_keywords(user_input, self._DEEPSEEK_KEYWORDS):
                return (
                    "Selected DeepSeek V4 Pro because the request involves "
                    "coding, editing, planning, logic, or algorithmic reasoning."
                )
            return "Selected DeepSeek V4 Pro (default text/coding model)."

        return f"Unknown model selected: {selected_model}"
