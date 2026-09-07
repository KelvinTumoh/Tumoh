"""Unit tests for the extension/plugin API."""

import asyncio
import json
from pathlib import Path

from ide_core.config.settings import IDESettings
from ide_core.extensions import ExtensionManager, ExtensionRegistry


def _write_plugin(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "hello_ext"
    plugin_dir.mkdir()
    manifest = {
        "name": "hello_ext",
        "version": "0.1.0",
        "entrypoint": "plugin.py",
        "hooks": ["editor.save.before"],
    }
    (plugin_dir / "ide_extension.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (plugin_dir / "plugin.py").write_text(
        "def register(registry):\n"
        "    registry.register('editor.save.before', lambda uri: f'saving {uri}')\n"
        "    registry.register('custom.hook', lambda x: x * 2)\n",
        encoding="utf-8",
    )


def test_registry_sync_dispatch():
    registry = ExtensionRegistry()
    registry.register("custom.hook", lambda x: x * 2)
    registry.register("custom.hook", lambda x: x + 1)

    results = registry.dispatch("custom.hook", 3)
    assert 6 in results
    assert 4 in results


def test_registry_async_dispatch():
    async def coro():
        registry = ExtensionRegistry()

        async def async_double(x):
            return x * 2

        registry.register("async.hook", async_double)
        registry.register("async.hook", lambda x: x + 1)

        results = await registry.dispatch_async("async.hook", 5)
        assert 10 in results
        assert 6 in results

    asyncio.run(coro())


def test_extension_manager_loads_plugin(tmp_path: Path):
    _write_plugin(tmp_path)
    settings = IDESettings(extensions_dir=str(tmp_path), enable_extensions=True)
    manager = ExtensionManager(settings)
    manager.load_all()

    assert len(manager.manifests) == 1
    assert manager.manifests[0].name == "hello_ext"

    results = manager.registry.dispatch("editor.save.before", "main.py")
    assert results == ["saving main.py"]


def test_extension_manager_disabled(tmp_path: Path):
    _write_plugin(tmp_path)
    settings = IDESettings(extensions_dir=str(tmp_path), enable_extensions=False)
    manager = ExtensionManager(settings)
    manager.load_all()

    assert manager.manifests == []
    assert manager.registry.hook_names() == []


def test_extension_manager_ignores_missing_directory():
    settings = IDESettings(extensions_dir="does_not_exist", enable_extensions=True)
    manager = ExtensionManager(settings)
    manager.load_all()

    assert manager.manifests == []
