"""Image, logo, and UI mockup generation with SVG placeholder fallbacks."""

from __future__ import annotations

import html
import uuid
from pathlib import Path
from typing import Optional

from ide_core.config.settings import IDESettings
from ide_core.logging.logger import IDELogger

from ..models import CreativeDomain, CreativeResult


class ImageGenerator:
    """Create placeholder SVG/PNG art, logos, and UI mockups."""

    def __init__(
        self,
        settings: Optional[IDESettings] = None,
        logger: Optional[IDELogger] = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._logger = logger or IDELogger(self._settings)

    async def generate(self, prompt: str, style: str = "default") -> CreativeResult:
        """Generate a generic SVG image preview."""
        rid = uuid.uuid4().hex
        path = self._write_svg(rid, "image", prompt, style)
        return CreativeResult(
            request_id=rid,
            success=True,
            domain=CreativeDomain.IMAGE,
            output_path=path,
            preview_data=Path(path).read_bytes(),
            message="SVG placeholder image generated",
            metadata={"style": style, "prompt": prompt},
        )

    async def generate_logo(
        self, app_name: str, style: str = "minimal"
    ) -> CreativeResult:
        """Generate a placeholder SVG logo for an application."""
        rid = uuid.uuid4().hex
        safe_name = html.escape(app_name)
        path = self._write_svg(rid, f"{app_name}-logo", f"Logo for {app_name}", style)
        return CreativeResult(
            request_id=rid,
            success=True,
            domain=CreativeDomain.LOGO,
            output_path=path,
            preview_data=Path(path).read_bytes(),
            message="SVG placeholder logo generated",
            metadata={"style": style, "app_name": app_name},
        )

    async def generate_ui_mockup(self, description: str) -> CreativeResult:
        """Generate a placeholder UI wireframe/mockup."""
        rid = uuid.uuid4().hex
        path = self._write_svg(
            rid,
            "ui-mockup",
            description,
            "wireframe",
            extra_shapes=True,
        )
        return CreativeResult(
            request_id=rid,
            success=True,
            domain=CreativeDomain.UI_MOCKUP,
            output_path=path,
            preview_data=Path(path).read_bytes(),
            message="SVG placeholder UI mockup generated",
            metadata={"description": description},
        )

    def _write_svg(
        self,
        request_id: str,
        label: str,
        prompt: str,
        style: str,
        extra_shapes: bool = False,
    ) -> str:
        out_dir = Path(self._settings.creative_tools_path)
        out_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{request_id}-{label}.svg"
        filepath = out_dir / filename

        shapes = ""
        if extra_shapes:
            shapes = (
                '<rect x="20" y="90" width="360" height="40" '
                'fill="#f0f0f0" stroke="#999"/>\n  '
                '<rect x="20" y="140" width="240" height="30" '
                'fill="#f0f0f0" stroke="#999"/>\n  '
                '<rect x="20" y="180" width="120" height="40" '
                'fill="#e0e0e0" stroke="#999"/>'
            )

        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="20" y="40" font-family="sans-serif" font-size="18" fill="#333">{html.escape(prompt[:80])}</text>
  <text x="20" y="70" font-family="sans-serif" font-size="14" fill="#666">Style: {html.escape(style)}</text>
  {shapes}
  <text x="20" y="270" font-family="sans-serif" font-size="12" fill="#999">Request: {request_id[:8]}</text>
</svg>"""

        filepath.write_text(svg, encoding="utf-8")
        return str(filepath)
