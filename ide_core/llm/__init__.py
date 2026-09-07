"""Lazy exports for the LLM subpackage."""


def __getattr__(name: str):
    if name == "ModelType":
        from ide_core.llm.smart_router import ModelType
        return ModelType
    if name == "SmartRouter":
        from ide_core.llm.smart_router import SmartRouter
        return SmartRouter
    if name == "UnifiedLLMClient":
        from ide_core.llm.unified_client import UnifiedLLMClient
        return UnifiedLLMClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ModelType", "SmartRouter", "UnifiedLLMClient"]
