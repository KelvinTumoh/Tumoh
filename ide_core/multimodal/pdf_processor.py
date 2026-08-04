"""PDF text, requirements, and image extraction with optional pypdf."""

from __future__ import annotations

import io
import re
from typing import Optional

from ide_core.config.settings import IDESettings
from ide_core.logging.logger import IDELogger

try:
    from pypdf import PdfReader

    _HAS_PYPDF = True
except Exception:
    try:
        from PyPDF2 import PdfReader

        _HAS_PYPDF = True
    except Exception:
        _HAS_PYPDF = False
        PdfReader = None  # type: ignore[assignment]


class PDFProcessor:
    """Extract text, requirements, and embedded images from PDF bytes."""

    def __init__(
        self,
        settings: Optional[IDESettings] = None,
        logger: Optional[IDELogger] = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._logger = logger or IDELogger(self._settings)

    def extract_text(self, pdf_bytes: bytes) -> str:
        """Return the PDF text content, or printable-strings fallback."""
        if not self._settings.enable_pdf_parsing:
            return self._fallback_text(pdf_bytes)

        if not _HAS_PYPDF or PdfReader is None:
            return self._fallback_text(pdf_bytes)

        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            return "\n".join(
                page.extract_text() or "" for page in reader.pages
            ).strip()
        except Exception as exc:
            self._logger.log_event("pdf_extraction_error", error=str(exc))
            return self._fallback_text(pdf_bytes)

    def extract_requirements(self, pdf_bytes: bytes) -> list[str]:
        """Parse requirement bullets and spec directives from PDF text."""
        text = self.extract_text(pdf_bytes)
        requirements: list[str] = []

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith(("-", "*", "•", "◦")):
                requirements.append(line)
                continue

            if re.match(r"^\d+[\.\)]\s", line):
                requirements.append(line)
                continue

            if re.match(
                r"^(REQ|TODO|MUST|SHALL|SHOULD|MAY)\b",
                line,
                re.IGNORECASE,
            ):
                requirements.append(line)

        return requirements

    def extract_images(self, pdf_bytes: bytes) -> list[bytes]:
        """Return embedded image byte payloads when pypdf is available."""
        if not self._settings.enable_pdf_parsing:
            return []

        if not _HAS_PYPDF or PdfReader is None:
            return []

        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            images: list[bytes] = []
            for page in reader.pages:
                for image in getattr(page, "images", []):
                    images.append(image.data)
            return images
        except Exception as exc:
            self._logger.log_event("pdf_image_extraction_error", error=str(exc))
            return []

    def _fallback_text(self, pdf_bytes: bytes) -> str:
        """Extract printable ASCII strings from raw PDF bytes."""
        strings = re.findall(rb"[\x20-\x7e]{4,}", pdf_bytes)
        return " ".join(
            s.decode("ascii", errors="ignore") for s in strings
        )
