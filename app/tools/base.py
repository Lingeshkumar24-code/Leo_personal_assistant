"""
Every LEO capability is implemented as a Tool (§32 Extensibility).
The planner selects tools by name; new tools can be added without touching
the orchestrator, planner, or UI.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.security.permissions import PermissionLevel


@dataclass
class ToolResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    verification: str | None = None  # human-readable statement of how success was verified


class Tool(ABC):
    name: str = "base.tool"
    description: str = ""
    permission_level: PermissionLevel = PermissionLevel.NORMAL
    # "implemented" tools do real work; "planned" tools exist only as
    # interface scaffolding and must raise NotImplementedError from run().
    status: str = "implemented"
    parameters_schema: dict[str, Any] = {}

    @abstractmethod
    def run(self, **kwargs) -> ToolResult:
        raise NotImplementedError

    def verify(self, result: ToolResult, **kwargs) -> ToolResult:
        """
        Default verification is a no-op that trusts `run()`'s own success flag.
        Tools where success can be independently checked (e.g. "is the window
        actually open?") should override this to implement the
        OBSERVE -> ACT -> OBSERVE -> VERIFY loop from §19 of the spec.
        """
        return result


class NotImplementedTool(Tool):
    """
    Base class for Phase 2+ capabilities that are scaffolded but not yet built.
    Calling `run()` always fails loudly and honestly instead of faking success,
    per §39 of the spec ("Do not simulate computer control").
    """

    status = "planned"

    def run(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=False,
            error=(
                f"'{self.name}' is not implemented yet (status=planned). "
                "See README.md 'Project status' for the implementation roadmap."
            ),
        )
