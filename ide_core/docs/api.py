"""Generate OpenAPI documentation from WebSocket and tool schemas."""

from __future__ import annotations

import json
from typing import Any

from ide_core.agent.tools import ToolRegistry


class OpenAPIDocs:
    """Build a simple OpenAPI 3.0 document for the IDE engine."""

    WEBSOCKET_MESSAGES = {
        "doc_open": {
            "uri": {"type": "string"},
            "language_id": {"type": "string"},
            "content": {"type": "string"},
        },
        "doc_edit": {
            "uri": {"type": "string"},
            "start_index": {"type": "integer"},
            "end_index": {"type": "integer"},
            "new_text": {"type": "string"},
        },
        "completion": {
            "uri": {"type": "string"},
            "offset": {"type": "integer"},
            "request_id": {"type": "integer"},
        },
        "pty_input": {"data": {"type": "string"}},
        "get_tree": {"path": {"type": "string"}},
        "get_project": {},
    }

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tool_registry = tool_registry

    def generate(self) -> dict[str, Any]:
        """Return an OpenAPI document as a dictionary."""
        tool_schemas = self._tool_registry.get_schemas()
        paths: dict[str, Any] = {}

        for name, props in self.WEBSOCKET_MESSAGES.items():
            paths[f"/ws/{name}"] = {
                "post": {
                    "summary": f"WebSocket {name} message",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "const": name},
                                        **props,
                                    },
                                }
                            }
                        }
                    },
                }
            }

        for tool in tool_schemas:
            fn = tool["function"]
            paths[f"/tools/{fn['name']}"] = {
                "post": {
                    "summary": fn.get("description", ""),
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": fn.get("parameters", {})
                            }
                        }
                    },
                }
            }

        return {
            "openapi": "3.0.3",
            "info": {
                "title": "IDE Engine API",
                "version": "1.0.0",
            },
            "paths": paths,
            "components": {
                "schemas": {
                    tool["function"]["name"]: tool["function"].get("parameters", {})
                    for tool in tool_schemas
                }
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize the OpenAPI document to JSON."""
        return json.dumps(self.generate(), indent=indent)
