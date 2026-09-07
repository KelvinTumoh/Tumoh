"""MIME and file-signature detection for multimodal content."""

from __future__ import annotations

from .models import InputType

_PDF_SIGNATURE = b"%PDF"
_PNG_SIGNATURE = b"\x89PNG"
_JPEG_SIGNATURE = b"\xff\xd8"
_GIF_SIGNATURES = (b"GIF87a", b"GIF89a")
_ZIP_SIGNATURE = b"PK\x03\x04"
_VOICE_MP3_SIGNATURES = (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")


def detect_mime_type(content: bytes) -> InputType:
    """Use file magic headers to resolve an AUTO input into a concrete type."""
    if not content:
        return InputType.TEXT

    if content.startswith(_PDF_SIGNATURE):
        return InputType.PDF

    if content.startswith(_PNG_SIGNATURE) or content.startswith(_JPEG_SIGNATURE):
        return InputType.IMAGE

    if any(content.startswith(sig) for sig in _GIF_SIGNATURES):
        return InputType.IMAGE

    if content.startswith(b"RIFF") and len(content) >= 12:
        # RIFF containers are commonly WAVE (audio) or WEBP (image).
        form = content[8:12].upper()
        if form == b"WAVE":
            return InputType.VOICE
        if form == b"WEBP":
            return InputType.IMAGE

    if any(content.startswith(sig) for sig in _VOICE_MP3_SIGNATURES):
        return InputType.VOICE

    if content.startswith(_ZIP_SIGNATURE):
        return InputType.DOCUMENT

    sample = content[:1024]
    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError:
        return InputType.IMAGE

    if all(32 <= ord(ch) < 127 or ch in "\r\n\t" for ch in text):
        return InputType.TEXT

    return InputType.IMAGE
