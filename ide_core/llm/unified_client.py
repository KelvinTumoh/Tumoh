"""Async single entry point for DeepSeek and Gemini chat completions."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
from pathlib import Path
from typing import Any

import google.generativeai as genai
from openai import AsyncOpenAI

from ide_core.config.settings import IDESettings
from ide_core.llm.smart_router import ModelType, SmartRouter

logger = logging.getLogger(__name__)


Attachment = str | Path | dict[str, Any]


class UnifiedLLMClient:
    """Async single entry point for DeepSeek and Gemini chat completions."""

    DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
    DEFAULT_GEMINI_MODEL = "gemini-1.5-pro"
    DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"

    # Normalise semantic attachment types from the chat layer to MIME types.
    _MIME_OVERRIDES = {
        "image": "image/png",
        "voice": "audio/wav",
        "audio": "audio/wav",
        "pdf": "application/pdf",
        "video": "video/mp4",
    }

    def __init__(self, settings: IDESettings | None = None):
        self.settings = settings or IDESettings()
        self.router = SmartRouter(self.settings)

        self._deepseek_client: AsyncOpenAI | None = None
        if self.settings.enable_deepseek and self.settings.deepseek_api_key:
            base_url = getattr(
                self.settings, "deepseek_base_url", self.DEFAULT_DEEPSEEK_BASE_URL
            )
            self._deepseek_client = AsyncOpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=base_url,
            )

        self._gemini_model: genai.GenerativeModel | None = None
        if self.settings.enable_gemini and self.settings.gemini_api_key:
            genai.configure(api_key=self.settings.gemini_api_key)
            model = getattr(
                self.settings, "gemini_model", self.DEFAULT_GEMINI_MODEL
            )
            self._gemini_model = genai.GenerativeModel(model)

    @staticmethod
    def _is_mime(value: str) -> bool:
        return "/" in value

    def _attachment_mime_type(self, attachment: Attachment) -> str | None:
        if isinstance(attachment, dict):
            mime = attachment.get("mime_type") or attachment.get("type") or ""
            if self._is_mime(mime):
                return mime
            return self._MIME_OVERRIDES.get(mime)

        path = Path(str(attachment))
        mime, _ = mimetypes.guess_type(str(path))
        return mime

    def _attachment_bytes(self, attachment: Attachment) -> bytes:
        if isinstance(attachment, dict):
            if "payload" in attachment:
                data = attachment["payload"]
                return data if isinstance(data, bytes) else str(data).encode()
            if "data" in attachment:
                data = attachment["data"]
                return data if isinstance(data, bytes) else str(data).encode()
            if "path" in attachment:
                return Path(str(attachment["path"])).read_bytes()
            raise ValueError("Attachment dict must contain 'path', 'data', or 'payload'.")
        return Path(str(attachment)).read_bytes()

    def _build_gemini_part(self, attachment: Attachment) -> genai.protos.Part:
        data = self._attachment_bytes(attachment)
        mime = self._attachment_mime_type(attachment)
        if not mime:
            mime = "application/octet-stream"
        return genai.protos.Part(
            inline_data=genai.protos.Blob(mime_type=mime, data=data)
        )

    def _build_gemini_contents(
        self,
        user_input: str,
        attachments: list[Attachment] | None,
    ) -> list[genai.protos.Part]:
        contents: list[genai.protos.Part] = [
            genai.protos.Part(text=user_input or "")
        ]
        for attachment in attachments or []:
            contents.append(self._build_gemini_part(attachment))
        return contents

    def _build_deepseek_messages(
        self,
        user_input: str,
        messages: list[dict[str, str]] | None,
    ) -> list[dict[str, str]]:
        if messages:
            messages = list(messages)
            if user_input:
                messages.append({"role": "user", "content": user_input})
            return messages
        return [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": user_input or ""},
        ]

    async def _deepseek_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int | None,
        stream: bool,
        reasoning_effort: str,
    ) -> dict[str, Any]:
        if not self._deepseek_client:
            raise RuntimeError("DeepSeek is not configured or disabled.")

        extra_body = {
            "thinking": {"type": "enabled"},
            "reasoning_effort": reasoning_effort,
        }
        model = getattr(
            self.settings, "deepseek_model", self.DEFAULT_DEEPSEEK_MODEL
        )

        try:
            response = await self._deepseek_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                extra_body=extra_body,
            )
        except Exception as exc:
            logger.exception("DeepSeek API call failed")
            raise RuntimeError(f"DeepSeek request failed: {exc}") from exc

        if stream:
            return {
                "content": "",
                "reasoning": None,
                "finish_reason": None,
                "usage": None,
                "stream": response,
            }

        choice = response.choices[0]
        message = choice.message
        reasoning = getattr(message, "reasoning_content", None)
        return {
            "content": message.content or "",
            "reasoning": reasoning,
            "finish_reason": choice.finish_reason,
            "usage": getattr(response, "usage", None),
        }

    async def _gemini_chat_completion(
        self,
        user_input: str,
        attachments: list[Attachment] | None,
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        if not self._gemini_model:
            raise RuntimeError("Gemini is not configured or disabled.")

        contents = self._build_gemini_contents(user_input, attachments)

        try:
            response = await asyncio.to_thread(
                self._gemini_model.generate_content,
                contents,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
        except Exception as exc:
            logger.exception("Gemini API call failed")
            raise RuntimeError(f"Gemini request failed: {exc}") from exc

        return {
            "content": response.text or "",
            "reasoning": None,
            "finish_reason": None,
            "usage": None,
        }

    def _format_response(
        self,
        model: ModelType,
        reason: str,
        raw: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": raw["content"],
            "model": model.value,
            "reason": reason,
            "reasoning": raw.get("reasoning"),
            "finish_reason": raw.get("finish_reason"),
            "usage": raw.get("usage"),
        }

    async def chat_completion(
        self,
        messages: list[dict[str, str]] | None = None,
        user_input: str = "",
        has_attachments: bool = False,
        attachment_type: str | None = None,
        attachments: list[Attachment] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        reasoning_effort: str = "medium",
    ) -> dict[str, Any]:
        """Async main entry point with automatic smart routing."""
        if attachments:
            has_attachments = True
            if not attachment_type:
                attachment_type = self._attachment_mime_type(attachments[0])

        model = self.router.route(user_input, has_attachments, attachment_type)
        reason = self.router.get_routing_reason(user_input, model)
        logger.info(f"🧠 Selected model: {model.value}")

        # Safe fallback: if the chosen provider is not configured, try the other one.
        if model == ModelType.DEEPSEEK and not self._deepseek_client:
            if self._gemini_model:
                logger.info("Falling back to Gemini because DeepSeek is not configured")
                model = ModelType.GEMINI
            else:
                return self._format_response(
                    model,
                    "DeepSeek is not configured.",
                    {
                        "content": (
                            "AI API keys not configured. "
                            "Please set GEMINI_API_KEY or DEEPSEEK_API_KEY in your environment."
                        ),
                        "reasoning": None,
                        "finish_reason": None,
                        "usage": None,
                    },
                )

        if model == ModelType.GEMINI and not self._gemini_model:
            if self._deepseek_client:
                logger.info("Falling back to DeepSeek because Gemini is not configured")
                model = ModelType.DEEPSEEK
            else:
                return self._format_response(
                    model,
                    "Gemini is not configured.",
                    {
                        "content": (
                            "AI API keys not configured. "
                            "Please set GEMINI_API_KEY or DEEPSEEK_API_KEY in your environment."
                        ),
                        "reasoning": None,
                        "finish_reason": None,
                        "usage": None,
                    },
                )

        if model == ModelType.GEMINI:
            raw = await self._gemini_chat_completion(
                user_input=user_input,
                attachments=attachments,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            messages = self._build_deepseek_messages(user_input, messages)
            raw = await self._deepseek_chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                reasoning_effort=reasoning_effort,
            )

        return self._format_response(model, reason, raw)
