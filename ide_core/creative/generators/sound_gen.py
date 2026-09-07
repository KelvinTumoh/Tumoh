"""Sound, music, and voiceover synthesis with WAV fallback buffers."""

from __future__ import annotations

import math
import struct
import uuid
import wave
from pathlib import Path

from ide_core.config.settings import IDESettings
from ide_core.logging.logger import IDELogger

from ..models import CreativeDomain, CreativeResult


class SoundGenerator:
    """Generate synthetic audio previews when external TTS/SFX APIs are absent."""

    def __init__(
        self,
        settings: IDESettings | None = None,
        logger: IDELogger | None = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._logger = logger or IDELogger(self._settings)

    async def generate_sound(self, description: str) -> CreativeResult:
        """Generate a short synthesized sound effect preview."""
        return self._write_wav(
            "sound",
            description,
            CreativeDomain.SOUND,
            duration=2,
            frequency=440,
        )

    async def generate_music(self, mood: str, duration: int = 10) -> CreativeResult:
        """Generate a placeholder music track."""
        return self._write_wav(
            "music",
            f"mood: {mood}",
            CreativeDomain.SOUND,
            duration=duration,
            frequency=262,
        )

    async def generate_voiceover(self, text: str, voice: str = "alloy") -> CreativeResult:
        """Generate a placeholder voiceover track."""
        # Rough heuristic: one second per ~20 characters, capped at 30 seconds.
        duration = min(max(2, len(text) // 20), 30)
        return self._write_wav(
            "voiceover",
            f"voice: {voice}",
            CreativeDomain.VOICEOVER,
            duration=duration,
            frequency=180,
        )

    def _write_wav(
        self,
        label: str,
        description: str,
        domain: CreativeDomain,
        duration: int,
        frequency: int,
    ) -> CreativeResult:
        rid = uuid.uuid4().hex
        out_dir = Path(self._settings.creative_tools_path)
        out_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{rid}-{label}.wav"
        filepath = out_dir / filename

        sample_rate = 44100
        num_samples = sample_rate * duration

        with wave.open(str(filepath), "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            for i in range(num_samples):
                value = int(
                    32767 * math.sin(2 * math.pi * frequency * i / sample_rate)
                )
                w.writeframes(struct.pack("<h", value))

        return CreativeResult(
            request_id=rid,
            success=True,
            domain=domain,
            output_path=str(filepath),
            preview_data=filepath.read_bytes(),
            message="Synthesized WAV preview generated",
            metadata={
                "description": description,
                "duration_seconds": duration,
                "frequency": frequency,
            },
        )
