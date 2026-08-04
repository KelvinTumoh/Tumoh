"""Unified chat integration layer that routes messages to IDE subsystems."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from ide_core.agent.orchestrator import AgentOrchestrator
from ide_core.config.settings import IDESettings
from ide_core.creative.agent_creative import CreativeAgent
from ide_core.creative.intent_engine import CreativeIntentEngine
from ide_core.creative.models import CreativeDomain, CreativeRequest, CreativeResult
from ide_core.multimodal.input_engine import MultimodalInputEngine
from ide_core.multimodal.models import InputType, MultimodalInput, ProcessedInput
from ide_core.personality.personality import FriendPersonality
from ide_core.smart_decision.assistant import SmartAssistant

from .models import ChatContext, ChatMessage, MessageType, _now_iso


class UnifiedChatIntegration:
    """Route chat messages to multimodal, creative, smart, and agent subsystems."""

    def __init__(
        self,
        settings: Optional[IDESettings] = None,
        multimodal: Optional[MultimodalInputEngine] = None,
        creative: Optional[CreativeAgent] = None,
        smart: Optional[SmartAssistant] = None,
        personality: Optional[FriendPersonality] = None,
        orchestrator: Optional[AgentOrchestrator] = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._multimodal = multimodal or MultimodalInputEngine(self._settings)
        self._creative = creative or CreativeAgent(self._settings)
        self._smart = smart or SmartAssistant(self._settings)
        self._personality = personality or FriendPersonality(self._settings)
        self._orchestrator = orchestrator
        self._intent = CreativeIntentEngine()

    async def route(
        self, message: ChatMessage, context: ChatContext
    ) -> list[ChatMessage]:
        """Process a chat message and return response messages."""
        if not self._settings.enable_chat:
            return [self._system(message, "Chat is currently disabled.")]

        if message.type in (MessageType.TEXT, MessageType.VOICE, MessageType.IMAGE, MessageType.PDF):
            processed = await self._process_multimodal(message)
            text = processed.raw_text

            if self._looks_creative(text) or message.type == MessageType.CREATIVE_REQUEST:
                return [self._decorate(await self._process_creative(text, message), context)]

            if self._orchestrator and processed.intent in ("create", "fix", "refactor"):
                try:
                    result = await self._orchestrator.run(text)
                    final = result[-1]["content"] if result else "Task complete."
                except Exception as exc:
                    final = f"[Agent task incomplete: {exc}]"
                return [self._decorate(self._text_response(message, final), context)]

            return [self._decorate(self._text_response(message, text), context)]

        if message.type == MessageType.CREATIVE_REQUEST:
            return [self._decorate(await self._process_creative(message.content, message), context)]

        return [self._system(message, f"Unsupported message type: {message.type.value}")]

    async def _process_multimodal(self, message: ChatMessage) -> ProcessedInput:
        if not self._settings.enable_multimodal:
            return ProcessedInput(
                input_id=message.message_id,
                raw_text=message.content,
                intent="general",
            )

        if message.type == MessageType.TEXT:
            payload = message.content.encode("utf-8")
            input_type = InputType.TEXT
        elif message.type == MessageType.VOICE:
            payload = self._extract_payload(message, "voice")
            input_type = InputType.VOICE
        elif message.type == MessageType.IMAGE:
            payload = self._extract_payload(message, "image")
            input_type = InputType.IMAGE
        elif message.type == MessageType.PDF:
            payload = self._extract_payload(message, "pdf")
            input_type = InputType.PDF
        else:
            payload = message.content.encode("utf-8")
            input_type = InputType.TEXT

        multimodal_input = MultimodalInput(
            input_id=message.message_id,
            input_type=input_type,
            content=payload,
            metadata=message.metadata,
            source="chat",
            tenant_id=message.tenant_id,
        )
        return await self._multimodal.process_input(multimodal_input)

    def _extract_payload(self, message: ChatMessage, kind: str) -> bytes:
        for attachment in message.attachments:
            if attachment.get("type") == kind:
                payload = attachment.get("payload") or attachment.get("data")
                if isinstance(payload, str):
                    return payload.encode("utf-8")
                if isinstance(payload, bytes):
                    return payload
        return message.content.encode("utf-8")

    def _looks_creative(self, text: str) -> bool:
        keywords = (
            "logo",
            "image",
            "graphic",
            "mockup",
            "ui",
            "sound",
            "music",
            "voice",
            "video",
            "tutorial",
            "demo",
            "draw",
            "illustration",
            "create",
            "generate",
        )
        t = text.lower()
        return any(k in t for k in keywords)

    async def _process_creative(
        self, text: str, message: ChatMessage
    ) -> ChatMessage:
        if not self._settings.enable_creative_agent:
            return self._text_response(message, "Creative agent is disabled.")

        request = self._intent.interpret_text(text)
        request.request_id = message.message_id
        request.tenant_id = message.tenant_id
        request.options = {**request.options, **message.metadata.get("options", {})}

        if "candidates" in message.metadata:
            request.options["candidates"] = message.metadata["candidates"]

        result = await self._creative.execute(request)
        return self._creative_result(message, result)

    def _text_response(self, source: ChatMessage, text: str) -> ChatMessage:
        return ChatMessage(
            message_id=uuid.uuid4().hex,
            room_id=source.room_id,
            tenant_id=source.tenant_id,
            sender_id="assistant",
            type=MessageType.TEXT,
            content=text,
            timestamp=_now_iso(),
        )

    def _creative_result(
        self, source: ChatMessage, result: CreativeResult
    ) -> ChatMessage:
        parts = [f"Created {result.domain.value}"]
        if result.output_path:
            parts.append(f"({result.output_path})")
        if result.message:
            parts.append(f"- {result.message}")
        if result.metadata.get("smart_reason"):
            parts.append(f"[{result.metadata['smart_reason']}]")

        attachment: dict[str, Any] = {"type": result.domain.value}
        if result.output_path:
            attachment["path"] = result.output_path
        if result.preview_data:
            attachment["preview"] = result.preview_data.decode("latin1", errors="replace")

        return ChatMessage(
            message_id=uuid.uuid4().hex,
            room_id=source.room_id,
            tenant_id=source.tenant_id,
            sender_id="assistant",
            type=MessageType.CREATIVE_RESULT,
            content=" ".join(parts),
            timestamp=_now_iso(),
            attachments=[attachment],
            metadata=result.metadata,
        )

    def _decorate(self, response: ChatMessage, context: ChatContext) -> ChatMessage:
        if not self._settings.chat_enable_friends or not self._settings.enable_friend_personality:
            return response

        if response.type == MessageType.CREATIVE_RESULT and response.content.startswith("Created"):
            celebrated = self._personality.interact(
                "celebrate",
                context.tenant_id,
                context.user_id,
                {"achievement_type": "milestone"},
            )
            if celebrated.get("celebration"):
                response.content = f"{celebrated['celebration']} {response.content}"
        else:
            response.content = self._personality.get_response(
                context.user_id,
                context.tenant_id,
                response.content,
            )
        return response

    def _system(self, source: ChatMessage, text: str) -> ChatMessage:
        return ChatMessage(
            message_id=uuid.uuid4().hex,
            room_id=source.room_id,
            tenant_id=source.tenant_id,
            sender_id="system",
            type=MessageType.SYSTEM,
            content=text,
            timestamp=_now_iso(),
        )
