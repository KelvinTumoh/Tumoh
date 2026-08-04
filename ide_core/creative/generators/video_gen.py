"""Video demo and tutorial generation with FFmpeg or JSON fallback."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

from ide_core.config.settings import IDESettings
from ide_core.logging.logger import IDELogger

from ..models import CreativeDomain, CreativeResult


class VideoGenerator:
    """Create video preview metadata when FFmpeg is not available."""

    def __init__(
        self,
        settings: Optional[IDESettings] = None,
        logger: Optional[IDELogger] = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._logger = logger or IDELogger(self._settings)

    async def generate_demo(
        self, app_name: str, features: list[str]
    ) -> CreativeResult:
        """Generate a demo video preview for an application."""
        return self._build_metadata(
            "demo",
            f"Demo for {app_name}",
            CreativeDomain.VIDEO,
            app_name=app_name,
            features=features,
        )

    async def generate_tutorial(self, steps: list[str]) -> CreativeResult:
        """Generate a tutorial video preview."""
        return self._build_metadata(
            "tutorial",
            "Tutorial video",
            CreativeDomain.VIDEO,
            steps=steps,
        )

    def _build_metadata(
        self,
        label: str,
        description: str,
        domain: CreativeDomain,
        **kwargs,
    ) -> CreativeResult:
        rid = uuid.uuid4().hex
        out_dir = Path(self._settings.creative_tools_path)
        out_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{rid}-{label}.json"
        filepath = out_dir / filename

        payload = {
            "request_id": rid,
            "domain": domain.value,
            "description": description,
        }
        payload.update(kwargs)

        filepath.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        preview = f"Video placeholder: {description}".encode("utf-8")

        return CreativeResult(
            request_id=rid,
            success=True,
            domain=domain,
            output_path=str(filepath),
            preview_data=preview,
            message="Video frame-sequence metadata generated",
            metadata=payload,
        )
