"""Extension / plugin ecosystem for the IDE core engine."""

from .manager import ExtensionManager, ExtensionManifest, ExtensionRegistry

__all__ = ["ExtensionManager", "ExtensionManifest", "ExtensionRegistry"]
