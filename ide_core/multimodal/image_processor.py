"""Image OCR, type detection, and description for agent context."""

from __future__ import annotations

import io

from ide_core.config.settings import IDESettings
from ide_core.logging.logger import IDELogger

try:
    import pytesseract
    from PIL import Image

    _HAS_OCR = True
    _HAS_PIL = True
except Exception:
    _HAS_OCR = False
    _HAS_PIL = False
    pytesseract = None  # type: ignore[assignment]
    Image = None  # type: ignore[assignment]


class ImageProcessor:
    """Extract text, detect visual type, and describe images without crashing."""

    def __init__(
        self,
        settings: IDESettings | None = None,
        logger: IDELogger | None = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._logger = logger or IDELogger(self._settings)

    def extract_text(self, image_bytes: bytes) -> str:
        """Return OCR text or a metadata-based fallback string."""
        if not self._settings.enable_image_ocr:
            return self._metadata_text(image_bytes)

        if not _HAS_OCR or pytesseract is None or Image is None:
            self._logger.log_event("image_ocr_unavailable", fallback=True)
            return self._metadata_text(image_bytes)

        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                text = pytesseract.image_to_string(
                    img,
                    lang=self._settings.ocr_language,
                )
            return text.strip() or self._metadata_text(image_bytes)
        except Exception as exc:
            self._logger.log_event("image_ocr_error", error=str(exc))
            return self._metadata_text(image_bytes)

    def detect_type(self, image_bytes: bytes) -> str:
        """Classify an image as mockup, diagram, screenshot, or code_snippet."""
        text = self.extract_text(image_bytes).lower()

        if any(kw in text for kw in ("mock", "wireframe", "prototype", "ui ")):
            return "mockup"

        if any(kw in text for kw in ("diagram", "flowchart", "graph", "->", "--")):
            return "diagram"

        if any(kw in text for kw in ("def ", "class ", "import ", "function")):
            return "code_snippet"

        if any(kw in text for kw in ("screenshot", "screen", "capture")):
            return "screenshot"

        # Header metadata heuristics for binary-only images.
        if image_bytes.startswith(b"\x89PNG") and b"Screenshot" in image_bytes[:200]:
            return "screenshot"

        # Default to the most common IDE context image type.
        return "screenshot"

    def describe(self, image_bytes: bytes) -> str:
        """Generate a short visual description for an agent prompt."""
        image_type = self.detect_type(image_bytes)
        dimensions = self._get_dimensions(image_bytes)
        return (
            f"Image type: {image_type} ({dimensions}). "
            f"Payload size: {len(image_bytes)} bytes."
        )

    def _metadata_text(self, image_bytes: bytes) -> str:
        if image_bytes.startswith(b"\x89PNG"):
            return "[Image: PNG format; OCR unavailable]"
        if image_bytes.startswith(b"\xff\xd8"):
            return "[Image: JPEG format; OCR unavailable]"
        if any(image_bytes.startswith(sig) for sig in (b"GIF87a", b"GIF89a")):
            return "[Image: GIF format; OCR unavailable]"
        if image_bytes.startswith(b"RIFF"):
            return "[Image: WebP format; OCR unavailable]"
        return "[Image: OCR unavailable]"

    def _get_dimensions(self, image_bytes: bytes) -> str:
        if not _HAS_PIL or Image is None:
            return "dimensions unknown"
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                return f"{img.width}x{img.height}"
        except Exception:
            return "dimensions unknown"
