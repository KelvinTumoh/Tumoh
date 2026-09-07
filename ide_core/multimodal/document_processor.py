"""Document extraction for .docx, .md, .txt, .json, and .csv."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile

from ide_core.config.settings import IDESettings
from ide_core.logging.logger import IDELogger

try:
    from docx import Document

    _HAS_DOCX = True
except Exception:
    _HAS_DOCX = False
    Document = None  # type: ignore[assignment]


class DocumentProcessor:
    """Extract plain text from common document formats."""

    def __init__(
        self,
        settings: IDESettings | None = None,
        logger: IDELogger | None = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._logger = logger or IDELogger(self._settings)

    def extract_text(self, file_bytes: bytes, file_extension: str) -> str:
        """Return decoded or parsed text for the supplied document bytes."""
        ext = file_extension.lstrip(".").lower()

        if ext == "docx":
            return self._extract_docx(file_bytes)

        if ext in ("md", "txt"):
            return self._decode_text(file_bytes)

        if ext == "json":
            return self._extract_json(file_bytes)

        if ext == "csv":
            return self._extract_csv(file_bytes)

        # Unknown extension: best-effort UTF-8 decoding.
        return self._decode_text(file_bytes)

    def _extract_docx(self, file_bytes: bytes) -> str:
        if not _HAS_DOCX or Document is None:
            return self._fallback_docx_text(file_bytes)

        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                if "word/document.xml" not in zf.namelist():
                    return self._fallback_docx_text(file_bytes)

            doc = Document(io.BytesIO(file_bytes))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as exc:
            self._logger.log_event("docx_extraction_error", error=str(exc))
            return self._fallback_docx_text(file_bytes)

    def _fallback_docx_text(self, file_bytes: bytes) -> str:
        """Manually unzip a .docx and strip XML tags when python-docx is missing."""
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                if "word/document.xml" in zf.namelist():
                    xml = zf.read("word/document.xml").decode(
                        "utf-8", errors="ignore"
                    )
                    text = re.sub(r"<[^>]+>", " ", xml)
                    return re.sub(r"\s+", " ", text).strip()
        except Exception:
            pass
        return self._decode_text(file_bytes)

    def _decode_text(self, file_bytes: bytes) -> str:
        for encoding in ("utf-8", "ascii", "latin-1"):
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        return file_bytes.decode("utf-8", errors="ignore")

    def _extract_json(self, file_bytes: bytes) -> str:
        try:
            data = json.loads(file_bytes)
            return json.dumps(data, indent=2)
        except Exception:
            return self._decode_text(file_bytes)

    def _extract_csv(self, file_bytes: bytes) -> str:
        try:
            text = self._decode_text(file_bytes)
            reader = csv.reader(io.StringIO(text))
            return "\n".join(" | ".join(row) for row in reader)
        except Exception:
            return self._decode_text(file_bytes)
