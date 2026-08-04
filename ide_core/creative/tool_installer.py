"""Non-destructive tool discovery and optional auto-installation."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from typing import Optional

from ide_core.config.settings import IDESettings
from ide_core.logging.logger import IDELogger


class ToolInstaller:
    """Check for and optionally install external creative tools."""

    def __init__(
        self,
        settings: Optional[IDESettings] = None,
        logger: Optional[IDELogger] = None,
    ) -> None:
        self._settings = settings or IDESettings()
        self._logger = logger or IDELogger(self._settings)

    async def ensure_tool(self, tool_name: str) -> bool:
        """Return True if the tool is available, or attempt a safe install."""
        if shutil.which(tool_name):
            return True

        if not self._settings.enable_auto_install:
            self._logger.log_event(
                "tool_install_skipped",
                tool=tool_name,
                auto_install=False,
            )
            return False

        return await self._try_install(tool_name)

    async def _try_install(self, tool_name: str) -> bool:
        """Attempt a platform-appropriate, non-blocking install."""
        platform = sys.platform
        package_managers: list[tuple[str, list[str]]] = []

        if platform.startswith("win"):
            package_managers = [
                ("choco", ["choco", "install", tool_name, "-y"]),
                ("winget", ["winget", "install", "--id", tool_name, "-e"]),
            ]
        elif platform == "darwin":
            package_managers = [("brew", ["brew", "install", tool_name])]
        else:
            package_managers = [
                ("apt-get", ["apt-get", "install", "-y", tool_name]),
                ("dnf", ["dnf", "install", "-y", tool_name]),
                ("pacman", ["pacman", "-S", "--noconfirm", tool_name]),
            ]

        for manager, command in package_managers:
            if shutil.which(manager):
                try:
                    result = await asyncio.to_thread(
                        subprocess.run,
                        command,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if result.returncode == 0:
                        self._logger.log_event(
                            "tool_installed",
                            tool=tool_name,
                            manager=manager,
                        )
                        return True
                except Exception as exc:
                    self._logger.log_event(
                        "tool_install_failed",
                        tool=tool_name,
                        manager=manager,
                        error=str(exc),
                    )

        # Python packages can sometimes be installed via pip as a last resort.
        if tool_name.lower() in ("openai", "pillow", "python-docx", "pypdf"):
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, "-m", "pip", "install", tool_name],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    self._logger.log_event(
                        "tool_installed_via_pip",
                        tool=tool_name,
                    )
                    return True
            except Exception as exc:
                self._logger.log_event(
                    "pip_install_failed",
                    tool=tool_name,
                    error=str(exc),
                )

        self._logger.log_event(
            "tool_install_fallback",
            tool=tool_name,
            instructions=f"Please install {tool_name} manually.",
        )
        return False
