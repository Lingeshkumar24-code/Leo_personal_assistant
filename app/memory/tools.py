from __future__ import annotations

from app.memory.store import long_term_memory
from app.security.permissions import PermissionLevel
from app.tools.base import Tool, ToolResult


class RememberTool(Tool):
    name = "memory.remember"
    description = "Store a fact or preference for later (e.g. a project path, a preference)."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
        "required": ["key", "value"],
    }

    def run(self, key: str, value: str, **kwargs) -> ToolResult:
        long_term_memory.remember(key, value)
        return ToolResult(success=True, data={"key": key, "value": value})

    def verify(self, result: ToolResult, **kwargs) -> ToolResult:
        if result.success:
            stored = long_term_memory.recall(result.data["key"])
            result.success = stored == result.data["value"]
        return result


class RecallTool(Tool):
    name = "memory.recall"
    description = "Retrieve a previously stored fact or preference, or all of them."
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {
        "type": "object",
        "properties": {"key": {"type": "string", "description": "Leave empty to list all"}},
    }

    def run(self, key: str | None = None, **kwargs) -> ToolResult:
        if key:
            value = long_term_memory.recall(key)
            if value is None:
                return ToolResult(success=False, error=f"No memory found for key '{key}'")
            return ToolResult(success=True, data={"key": key, "value": value})
        return ToolResult(success=True, data={"preferences": long_term_memory.all_preferences()})
