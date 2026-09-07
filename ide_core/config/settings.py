"""Pydantic-settings based configuration for the IDE engine."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IDESettings(BaseSettings):
    """Production and development settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    default_model: str = "gpt-4o"
    default_temperature: float = 0.2
    editor_theme: str = "vs-dark"
    lsp_python_command: str = "pylsp"
    lsp_typescript_command: str = "typescript-language-server --stdio"
    directory_exclusions: list[str] = Field(
        default_factory=lambda: [
            "__pycache__",
            "node_modules",
            ".git",
            ".venv",
            "venv",
        ]
    )
    jwt_secret: str = "dev-secret-change-in-production-32bytes"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60
    log_level: str = "INFO"
    log_path: str = "ide_engine.log"
    ide_host: str = "localhost"
    ide_port: int = 8765
    enable_multi_tenant: bool = False
    tenant_storage_path: str = ".ide_tenants"
    base_domain: str = "localhost"
    tenant_cache_ttl: int = 300

    # Multimodal feature flags
    enable_multimodal: bool = True
    enable_voice_input: bool = True
    enable_image_ocr: bool = True
    enable_pdf_parsing: bool = True
    voice_language: str = "en-US"
    ocr_language: str = "eng"

    # Creative agent feature flags
    enable_creative_agent: bool = True
    enable_auto_install: bool = True
    creative_tools_path: str = ".creative_tools"
    preferred_image_model: str = "dalle"
    preferred_tts_model: str = "openai"

    # Smart decision feature flags
    enable_smart_decisions: bool = True
    preference_storage_path: str = "data/preferences"
    auto_learn_from_feedback: bool = True
    decision_explain_level: str = "friendly"

    # Friend personality feature flags
    enable_friend_personality: bool = True
    personality_traits: dict = Field(
        default_factory=lambda: {
            "friendly": 0.9,
            "helpful": 0.95,
            "creative": 0.85,
        }
    )
    personality_storage_path: str = "data/personality"
    auto_celebrate: bool = True
    auto_suggest_help: bool = True

    # Smart AI routing / multi-provider LLM
    deepseek_api_key: str | None = None
    gemini_api_key: str | None = None
    enable_deepseek: bool = True
    enable_gemini: bool = True
    enable_smart_routing: bool = True
    routing_default_model: str = "deepseek"

    # Unified chat feature flags
    enable_chat: bool = True
    chat_websocket_path: str = "/ws/chat"
    chat_message_history_limit: int = 100
    chat_presence_timeout: int = 60
    chat_enable_friends: bool = True

    # Security / sandboxing settings
    enable_security_manager: bool = True
    allowed_shell_commands: list[str] = Field(default_factory=list)
    blocked_shell_commands: list[str] = Field(
        default_factory=lambda: [
            "rm -rf",
            "sudo",
            "mkfs",
            "dd if=",
            "shutdown",
            "reboot",
            "format",
            "> /dev/",
            "| sh",
            "curl |",
            "wget |",
        ]
    )
    require_confirmation_patterns: list[str] = Field(
        default_factory=lambda: [
            "rm ",
            "sudo",
            "git push",
            "git reset",
            "git clean",
            "docker",
            "curl",
            "wget",
            "pip install",
            "npm install",
            "yarn",
        ]
    )
    audit_log_path: str = "security.log"

    # Extension / plugin ecosystem
    enable_extensions: bool = True
    extensions_dir: str = "extensions"
