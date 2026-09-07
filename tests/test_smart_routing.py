"""Tests for the smart AI routing layer."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from ide_core.config.settings import IDESettings
from ide_core.llm import ModelType, SmartRouter, UnifiedLLMClient


def _run(coro):
    """Run an async coroutine inside a sync pytest test."""
    return asyncio.run(coro)


class TestSmartRouter:
    """Routing decisions for DeepSeek and Gemini."""

    def test_code_goes_to_deepseek(self):
        settings = IDESettings()
        router = SmartRouter(settings)
        model = router.route("write a python function that sorts a list", False, None)
        assert model == ModelType.DEEPSEEK

    def test_edits_goes_to_deepseek(self):
        settings = IDESettings()
        router = SmartRouter(settings)
        model = router.route("refactor this bug and fix the exception", False, None)
        assert model == ModelType.DEEPSEEK

    def test_planning_goes_to_deepseek(self):
        settings = IDESettings()
        router = SmartRouter(settings)
        model = router.route("plan the database api architecture", False, None)
        assert model == ModelType.DEEPSEEK

    def test_image_attachment_goes_to_gemini(self):
        settings = IDESettings()
        router = SmartRouter(settings)
        model = router.route(
            "what is in this file?", True, "image/png"
        )
        assert model == ModelType.GEMINI

    def test_pdf_attachment_goes_to_gemini(self):
        settings = IDESettings()
        router = SmartRouter(settings)
        model = router.route(
            "summarise this document", True, "application/pdf"
        )
        assert model == ModelType.GEMINI

    def test_voice_attachment_goes_to_gemini(self):
        settings = IDESettings()
        router = SmartRouter(settings)
        model = router.route(
            "transcribe this clip", True, "audio/wav"
        )
        assert model == ModelType.GEMINI

    def test_video_attachment_goes_to_gemini(self):
        settings = IDESettings()
        router = SmartRouter(settings)
        model = router.route(
            "describe the video", True, "video/mp4"
        )
        assert model == ModelType.GEMINI

    def test_design_text_goes_to_gemini(self):
        settings = IDESettings()
        router = SmartRouter(settings)
        model = router.route("create a wireframe mockup for this ui", False, None)
        assert model == ModelType.GEMINI

    def test_ocr_text_goes_to_gemini(self):
        settings = IDESettings()
        router = SmartRouter(settings)
        model = router.route("scan and ocr the uploaded document", False, None)
        assert model == ModelType.GEMINI

    def test_generic_fallback_is_deepseek(self):
        settings = IDESettings()
        router = SmartRouter(settings)
        model = router.route("hello", False, None)
        assert model == ModelType.DEEPSEEK

    def test_disabled_smart_routing_uses_default(self):
        settings = IDESettings(
            enable_smart_routing=False,
            routing_default_model="gemini",
        )
        router = SmartRouter(settings)
        model = router.route("write some code", False, None)
        assert model == ModelType.GEMINI

    def test_routing_reason_matches_selected_model(self):
        settings = IDESettings()
        router = SmartRouter(settings)
        reason = router.get_routing_reason(
            "write a python class", ModelType.DEEPSEEK
        )
        assert "DeepSeek" in reason

    def test_routing_reason_for_gemini(self):
        settings = IDESettings()
        router = SmartRouter(settings)
        reason = router.get_routing_reason(
            "make a logo sketch", ModelType.GEMINI
        )
        assert "Gemini" in reason


class TestUnifiedLLMClient:
    """Mocked calls to DeepSeek and Gemini."""

    @patch("ide_core.llm.unified_client.AsyncOpenAI")
    async def _deepseek_call(self, mock_async_openai):
        settings = IDESettings(
            deepseek_api_key="fake-deepseek",
            enable_gemini=False,
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="DeepSeek reply",
                    reasoning_content="reasoning text",
                ),
                finish_reason="stop",
            )
        ]
        mock_response.usage = {"total_tokens": 7}
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )
        mock_async_openai.return_value = mock_client

        client = UnifiedLLMClient(settings)
        result = await client.chat_completion(
            user_input="write a function",
            reasoning_effort="high",
        )
        return result, mock_async_openai, mock_client

    def test_deepseek_call(self):
        result, mock_async_openai, mock_client = _run(self._deepseek_call())

        assert result["content"] == "DeepSeek reply"
        assert result["model"] == "deepseek"
        assert result["reasoning"] == "reasoning text"
        assert result["finish_reason"] == "stop"
        assert result["usage"] == {"total_tokens": 7}

        mock_async_openai.assert_called_once_with(
            api_key="fake-deepseek",
            base_url=UnifiedLLMClient.DEFAULT_DEEPSEEK_BASE_URL,
        )
        mock_client.chat.completions.create.assert_awaited_once()
        call = mock_client.chat.completions.create.await_args
        assert call.kwargs["model"] == UnifiedLLMClient.DEFAULT_DEEPSEEK_MODEL
        assert call.kwargs["extra_body"]["reasoning_effort"] == "high"
        assert call.kwargs["extra_body"]["thinking"]["type"] == "enabled"

    @patch("ide_core.llm.unified_client.genai")
    async def _gemini_call(self, mock_genai):
        settings = IDESettings(
            gemini_api_key="fake-gemini",
            enable_deepseek=False,
        )

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Gemini reply"
        mock_model.generate_content = MagicMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model

        client = UnifiedLLMClient(settings)
        result = await client.chat_completion(
            user_input="describe this image",
            attachments=[{"type": "image", "payload": b"\x89PNG"}],
        )
        return result, mock_genai, mock_model

    def test_gemini_call(self):
        result, mock_genai, mock_model = _run(self._gemini_call())

        assert result["content"] == "Gemini reply"
        assert result["model"] == "gemini"

        mock_genai.configure.assert_called_once_with(api_key="fake-gemini")
        mock_genai.GenerativeModel.assert_called_once_with(
            UnifiedLLMClient.DEFAULT_GEMINI_MODEL
        )
        mock_model.generate_content.assert_called_once()

    @patch("ide_core.llm.unified_client.genai")
    @patch("ide_core.llm.unified_client.AsyncOpenAI")
    async def _attachment_detection(self, mock_async_openai, mock_genai):
        settings = IDESettings(
            deepseek_api_key="fake-deepseek",
            gemini_api_key="fake-gemini",
        )

        mock_genai.GenerativeModel.return_value = MagicMock()

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock()
        )
        mock_async_openai.return_value = mock_client

        client = UnifiedLLMClient(settings)

        # An image attachment should be routed to Gemini.
        image_result = await client.chat_completion(
            user_input="what is this?",
            attachments=[{"type": "image", "payload": b"\x89PNG"}],
        )

        # A pure text coding prompt should be routed to DeepSeek.
        text_result = await client.chat_completion(
            user_input="fix the bug in this class",
        )

        return image_result, text_result

    def test_attachment_detection_routes_correctly(self):
        image_result, text_result = _run(self._attachment_detection())
        assert image_result["model"] == "gemini"
        assert text_result["model"] == "deepseek"

    def test_deepseek_live_call(self):
        """Test that the DeepSeek API is responding with the configured key."""
        settings = IDESettings()
        if not settings.deepseek_api_key:
            import pytest

            pytest.skip("No DeepSeek API key found")

        client = UnifiedLLMClient(settings)

        async def _call():
            return await client.chat_completion(
                user_input="Return the word 'Hello'",
            )

        result = _run(_call())
        assert result["model"] == "deepseek"
        assert "Hello" in result["content"]
