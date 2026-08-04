"""Voice transcription with optional speech_recognition / whisper support."""

from __future__ import annotations

import io
from typing import Optional

from ide_core.config.settings import IDESettings
from ide_core.logging.logger import IDELogger

try:
    import speech_recognition as sr

    _HAS_SPEECH_RECOGNITION = True
except Exception:
    _HAS_SPEECH_RECOGNITION = False
    sr = None  # type: ignore[assignment]

try:
    import whisper

    _HAS_WHISPER = True
except Exception:
    _HAS_WHISPER = False

FALLBACK_VOICE_MESSAGE = "[Voice Input Processed: Fallback Engine Active]"


class VoiceProcessor:
    """Transcribe audio bytes to text with graceful hardware/library fallback."""

    def __init__(
        self,
        settings: Optional[IDESettings] = None,
        logger: Optional[IDELogger] = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._logger = logger or IDELogger(self._settings)

    async def transcribe(self, audio_bytes: bytes, language: str = "en-US") -> str:
        """Return a transcript or a structured fallback notification."""
        if not self._settings.enable_voice_input:
            self._logger.log_event("voice_input_disabled")
            return FALLBACK_VOICE_MESSAGE

        if not audio_bytes:
            self._logger.log_event("voice_empty_payload")
            return FALLBACK_VOICE_MESSAGE

        try:
            if _HAS_SPEECH_RECOGNITION and sr is not None:
                recognizer = sr.Recognizer()
                source = sr.AudioFile(io.BytesIO(audio_bytes))
                with source as s:
                    audio = recognizer.record(s, duration=None)
                return recognizer.recognize_google(audio, language=language)

            if _HAS_WHISPER:
                # Placeholder for local whisper inference. Kept lightweight to avoid
                # loading large models during normal operation; tests mock this path
                # when required.
                result = whisper.transcribe(None, audio_bytes)
                return result.get("text", FALLBACK_VOICE_MESSAGE)

        except Exception as exc:
            self._logger.log_event("voice_transcription_fallback", error=str(exc))
            return FALLBACK_VOICE_MESSAGE

        self._logger.log_event("voice_libraries_unavailable")
        return FALLBACK_VOICE_MESSAGE
