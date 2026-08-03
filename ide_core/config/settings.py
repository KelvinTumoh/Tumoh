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
    directory_exclusions: list[str] = Field(default_factory=lambda: ["__pycache__", "node_modules", ".git", ".venv", "venv"])
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60
    log_level: str = "INFO"
    log_path: str = "ide_engine.log"
    ide_host: str = "localhost"
    ide_port: int = 8765
