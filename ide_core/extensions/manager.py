"""Minimal extension manager with a hook registry."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ide_core.config.settings import IDESettings


class ExtensionManifest(BaseModel):
    """Validated plugin metadata."""

    name: str
    version: str
    entrypoint: str
    hooks: list[str] = Field(default_factory=list)
    author: str = ""
    description: str = ""


class ExtensionRegistry:
    """Central hook registry that extensions can register and the engine can dispatch."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def register(self, hook_name: str, handler: Callable[..., Any]) -> None:
        """Register a handler for a named hook."""
        self._hooks[hook_name].append(handler)

    def dispatch(self, hook_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        """Dispatch a hook to all registered synchronous handlers."""
        results: list[Any] = []
        for handler in self._hooks.get(hook_name, []):
            try:
                results.append(handler(*args, **kwargs))
            except Exception:
                pass
        return results

    async def dispatch_async(
        self, hook_name: str, *args: Any, **kwargs: Any
    ) -> list[Any]:
        """Dispatch a hook to all registered handlers, awaiting coroutines."""
        results: list[Any] = []
        for handler in self._hooks.get(hook_name, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    results.append(await handler(*args, **kwargs))
                else:
                    results.append(handler(*args, **kwargs))
            except Exception:
                pass
        return results

    def hook_names(self) -> list[str]:
        """Return the names of all registered hooks."""
        return list(self._hooks.keys())


class ExtensionManager:
    """Discover, validate, and load plugins from the configured extensions directory."""

    def __init__(self, settings: IDESettings | None = None) -> None:
        self._settings = settings or IDESettings()
        self._registry = ExtensionRegistry()
        self._manifests: list[ExtensionManifest] = []

    @property
    def registry(self) -> ExtensionRegistry:
        return self._registry

    @property
    def manifests(self) -> list[ExtensionManifest]:
        return list(self._manifests)

    def load_all(self) -> None:
        """Load every valid extension found in ``extensions_dir``."""
        if not self._settings.enable_extensions:
            return

        ext_dir = Path(self._settings.extensions_dir)
        if not ext_dir.is_dir():
            return

        for manifest_path in ext_dir.glob("*/ide_extension.json"):
            try:
                self._load_from_manifest(manifest_path)
            except Exception:
                continue

    def _load_from_manifest(self, manifest_path: Path) -> None:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = ExtensionManifest(**data)
        entry = manifest_path.parent / manifest.entrypoint
        self._load_module(entry, manifest)

    def _load_module(self, path: Path, manifest: ExtensionManifest) -> None:
        module_name = f"ide_extension.{manifest.name}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load extension {manifest.name} from {path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        register = getattr(module, "register", None)
        if callable(register):
            register(self._registry)

        self._manifests.append(manifest)
