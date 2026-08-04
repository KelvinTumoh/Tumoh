"""Mock-driven tests for the multimodal input engine and processors."""

from __future__ import annotations

import asyncio
import io
import json
import zipfile
from unittest.mock import MagicMock

import pytest

from ide_core.config.settings import IDESettings
from ide_core.multimodal import InputType, MultimodalInput, MultimodalInputEngine, ProcessedInput
from ide_core.multimodal.image_processor import ImageProcessor
from ide_core.multimodal.models import InputType as InputTypeEnum
from ide_core.multimodal.pdf_processor import PDFProcessor
from ide_core.multimodal.utils import detect_mime_type
from ide_core.multimodal.voice_processor import VoiceProcessor


# ---------------------------------------------------------------------------
# Voice processor
# ---------------------------------------------------------------------------


def _fake_speech_recognition_module():
    """Build a minimal mock for the speech_recognition package."""
    recognizer = MagicMock()
    recognizer.record = MagicMock(return_value="audio_data")
    recognizer.recognize_google = MagicMock(return_value="hello world")

    source_ctx = MagicMock(
        __enter__=MagicMock(return_value=None),
        __exit__=MagicMock(return_value=False),
    )

    fake_sr = MagicMock()
    fake_sr.Recognizer = MagicMock(return_value=recognizer)
    fake_sr.AudioFile = MagicMock(return_value=source_ctx)
    return fake_sr


def test_voice_transcription_mock(monkeypatch) -> None:
    from ide_core.multimodal import voice_processor as vp

    monkeypatch.setattr(vp, "_HAS_SPEECH_RECOGNITION", True)
    monkeypatch.setattr(vp, "sr", _fake_speech_recognition_module())

    settings = IDESettings(enable_voice_input=True)
    processor = VoiceProcessor(settings)
    result = asyncio.run(processor.transcribe(b"fake wav bytes"))

    assert result == "hello world"


def test_voice_transcription_fallback_when_disabled() -> None:
    settings = IDESettings(enable_voice_input=False)
    processor = VoiceProcessor(settings)
    result = asyncio.run(processor.transcribe(b"fake wav bytes"))

    assert result == "[Voice Input Processed: Fallback Engine Active]"


def test_voice_transcription_fallback_when_empty() -> None:
    settings = IDESettings(enable_voice_input=True)
    processor = VoiceProcessor(settings)
    result = asyncio.run(processor.transcribe(b""))

    assert result == "[Voice Input Processed: Fallback Engine Active]"


# ---------------------------------------------------------------------------
# Image processor
# ---------------------------------------------------------------------------


def _mock_image_module(monkeypatch, text: str):
    from ide_core.multimodal import image_processor as ip

    monkeypatch.setattr(ip, "_HAS_OCR", True)
    monkeypatch.setattr(ip, "_HAS_PIL", True)

    fake_img = MagicMock(width=800, height=600)
    fake_img.__enter__ = MagicMock(return_value=fake_img)
    fake_img.__exit__ = MagicMock(return_value=False)

    fake_pil = MagicMock()
    fake_pil.open = MagicMock(return_value=fake_img)
    monkeypatch.setattr(ip, "Image", fake_pil)

    fake_tesseract = MagicMock()
    fake_tesseract.image_to_string = MagicMock(return_value=text)
    monkeypatch.setattr(ip, "pytesseract", fake_tesseract)


def test_image_ocr_and_type_detection_mockup(monkeypatch) -> None:
    from ide_core.multimodal import image_processor as ip

    _mock_image_module(monkeypatch, "wireframe mockup")

    settings = IDESettings(enable_image_ocr=True)
    processor = ImageProcessor(settings)
    png = b"\x89PNG\r\n\x1a\n"

    text = processor.extract_text(png)
    assert text == "wireframe mockup"

    image_type = processor.detect_type(png)
    assert image_type == "mockup"

    description = processor.describe(png)
    assert "mockup" in description
    assert "800x600" in description


def test_image_type_detection_code_snippet(monkeypatch) -> None:
    from ide_core.multimodal import image_processor as ip

    _mock_image_module(monkeypatch, "def hello():\n    pass")

    settings = IDESettings(enable_image_ocr=True)
    processor = ImageProcessor(settings)
    png = b"\x89PNG\r\n\x1a\n"

    assert processor.extract_text(png) == "def hello():\n    pass"
    assert processor.detect_type(png) == "code_snippet"


def test_image_type_detection_diagram(monkeypatch) -> None:
    from ide_core.multimodal import image_processor as ip

    _mock_image_module(monkeypatch, "flowchart -> graph")

    settings = IDESettings(enable_image_ocr=True)
    processor = ImageProcessor(settings)
    png = b"\x89PNG\r\n\x1a\n"

    assert processor.detect_type(png) == "diagram"


def test_image_ocr_graceful_fallback_when_disabled() -> None:
    settings = IDESettings(enable_image_ocr=False)
    processor = ImageProcessor(settings)
    png = b"\x89PNG\r\n\x1a\n"

    text = processor.extract_text(png)
    assert "PNG format" in text


# ---------------------------------------------------------------------------
# PDF processor
# ---------------------------------------------------------------------------


def _mock_pdf_reader(monkeypatch, page_text: str, image_data: bytes | None = None):
    from ide_core.multimodal import pdf_processor as pp

    monkeypatch.setattr(pp, "_HAS_PYPDF", True)

    fake_page = MagicMock()
    fake_page.extract_text = MagicMock(return_value=page_text)
    if image_data is not None:
        fake_image = MagicMock(data=image_data)
        fake_page.images = [fake_image]
    else:
        fake_page.images = []

    fake_reader = MagicMock()
    fake_reader.pages = [fake_page]

    fake_PdfReader = MagicMock(return_value=fake_reader)
    monkeypatch.setattr(pp, "PdfReader", fake_PdfReader)

    return fake_reader, fake_page


def test_pdf_text_and_requirements_extraction_mock(monkeypatch) -> None:
    from ide_core.multimodal import pdf_processor as pp

    text = (
        "- Must implement login\n"
        "- Need a dashboard\n"
        "REQ-1: user authentication flow\n"
        "1. Users must sign in"
    )
    _mock_pdf_reader(monkeypatch, text)

    settings = IDESettings(enable_pdf_parsing=True)
    processor = PDFProcessor(settings)
    pdf_bytes = b"%PDF-1.4 fake"

    extracted = processor.extract_text(pdf_bytes)
    assert "Must implement login" in extracted

    requirements = processor.extract_requirements(pdf_bytes)
    assert "- Must implement login" in requirements
    assert "REQ-1: user authentication flow" in requirements
    assert "1. Users must sign in" in requirements

    # PdfReader is created once per call; image count resets on next call.
    _mock_pdf_reader(monkeypatch, text, image_data=b"raw_image")
    images = processor.extract_images(pdf_bytes)
    assert images == [b"raw_image"]


def test_pdf_graceful_fallback_without_pypdf() -> None:
    settings = IDESettings(enable_pdf_parsing=False)
    processor = PDFProcessor(settings)
    pdf_bytes = b"%PDF-1.4 hello world text"

    text = processor.extract_text(pdf_bytes)
    assert "hello" in text
    assert "world" in text


# ---------------------------------------------------------------------------
# Document processor
# ---------------------------------------------------------------------------


def _build_minimal_docx() -> bytes:
    """Create a valid ZIP payload with word/document.xml for docx tests."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("word/document.xml", "<w:document><w:p>Hello</w:p></w:document>")
    return buffer.getvalue()


def test_document_parsing_docx_md_txt(monkeypatch) -> None:
    from ide_core.multimodal import document_processor as dp
    from ide_core.multimodal.document_processor import DocumentProcessor

    fake_para = MagicMock(text="Hello docx")
    fake_doc = MagicMock(paragraphs=[fake_para])
    fake_Document = MagicMock(return_value=fake_doc)

    monkeypatch.setattr(dp, "_HAS_DOCX", True)
    monkeypatch.setattr(dp, "Document", fake_Document)

    processor = DocumentProcessor()
    docx_bytes = _build_minimal_docx()

    assert processor.extract_text(docx_bytes, "docx") == "Hello docx"
    assert processor.extract_text(b"# Markdown", "md") == "# Markdown"
    assert processor.extract_text(b"plain text", "txt") == "plain text"
    assert processor.extract_text(json.dumps({"a": 1}).encode(), "json") == json.dumps(
        {"a": 1}, indent=2
    )
    assert "a | b" in processor.extract_text(b"a,b\n1,2", "csv")


def test_document_fallback_without_docx() -> None:
    from ide_core.multimodal.document_processor import DocumentProcessor

    processor = DocumentProcessor()
    docx_bytes = _build_minimal_docx()

    result = processor.extract_text(docx_bytes, "docx")
    assert "Hello" in result


# ---------------------------------------------------------------------------
# MIME auto detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"%PDF-1.4", InputType.PDF),
        (b"\x89PNG\r\n\x1a\n", InputType.IMAGE),
        (b"\xff\xd8\xff\xe0", InputType.IMAGE),
        (b"GIF89a", InputType.IMAGE),
        (b"RIFF\x00\x00\x00\x00WAVE", InputType.VOICE),
        (b"ID3\x04\x00", InputType.VOICE),
        (b"PK\x03\x04", InputType.DOCUMENT),
        (b"hello world", InputType.TEXT),
    ],
)
def test_detect_mime_type(content: bytes, expected: InputType) -> None:
    assert detect_mime_type(content) == expected


# ---------------------------------------------------------------------------
# MultimodalInputEngine
# ---------------------------------------------------------------------------


def test_engine_respects_feature_flag() -> None:
    settings = IDESettings(enable_multimodal=False)
    engine = MultimodalInputEngine(settings)
    payload = MultimodalInput(
        input_id="1",
        input_type=InputType.TEXT,
        content=b"hello",
    )
    result = asyncio.run(engine.process_input(payload))

    assert "disabled" in result.raw_text
    assert result.intent == "none"


def test_engine_processes_text_and_infers_intent() -> None:
    settings = IDESettings(enable_multimodal=True)
    engine = MultimodalInputEngine(settings)
    payload = MultimodalInput(
        input_id="2",
        input_type=InputType.TEXT,
        content=b"Create a new function that adds two numbers",
    )
    result = asyncio.run(engine.process_input(payload))

    assert "Create a new function" in result.raw_text
    assert result.intent == "create"


def test_engine_routes_auto_input() -> None:
    settings = IDESettings(enable_multimodal=True)
    engine = MultimodalInputEngine(settings)
    payload = MultimodalInput(
        input_id="3",
        input_type=InputType.AUTO,
        content=b"%PDF-1.4 hello",
    )
    result = asyncio.run(engine.process_input(payload))

    assert "hello" in result.raw_text


# ---------------------------------------------------------------------------
# Agent context formatter
# ---------------------------------------------------------------------------


def test_to_agent_context() -> None:
    processed = ProcessedInput(
        input_id="ctx-1",
        raw_text="Please fix the `login.py` file",
        intent="fix",
        entities=["login.py"],
        summary="Fix login file",
        extracted_assets={"images": 0},
    )

    context = MultimodalInputEngine().to_agent_context(processed)

    assert "## Multimodal Input: ctx-1" in context
    assert "**Intent:** fix" in context
    assert "**Raw Text:**" in context
    assert "login.py" in context
    assert "**Summary:** Fix login file" in context
    assert "**Extracted Assets:**" in context
    assert '"images": 0' in context
