from __future__ import annotations

from dataclasses import dataclass, field

from app.tools.base import Tool


@dataclass
class ToolRegistry:
    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def implemented(self) -> list[Tool]:
        return [t for t in self._tools.values() if t.status == "implemented"]

    def planned(self) -> list[Tool]:
        return [t for t in self._tools.values() if t.status == "planned"]

    def as_tool_specs(self):
        """Convert to provider-agnostic ToolSpec list for tool_call()."""
        from app.providers.base import ToolSpec

        return [
            ToolSpec(
                name=t.name,
                description=t.description,
                parameters=t.parameters_schema or {"type": "object", "properties": {}},
            )
            for t in self._tools.values()
        ]


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()

    # Phase 8 - File system (implemented)
    from app.filesystem.tools import (
        CreateFolderTool,
        FindFilesTool,
        MoveFileTool,
        ReadFileTool,
        RenameFileTool,
    )

    registry.register(FindFilesTool())
    registry.register(ReadFileTool())
    registry.register(CreateFolderTool())
    registry.register(MoveFileTool())
    registry.register(RenameFileTool())
    from app.filesystem.tools import DeleteFileTool

    registry.register(DeleteFileTool())

    # Phase 10 - Memory (implemented, exposed as tools too)
    from app.memory.tools import RememberTool, RecallTool

    registry.register(RememberTool())
    registry.register(RecallTool())

    # Phase 3 - Computer control (implemented; needs a real display/OS to act)
    from app.computer.tools import (
        OpenApplicationTool,
        CloseApplicationTool,
        ClickTool,
        TypeTextTool,
        HotkeyTool,
        TakeScreenshotTool,
    )

    registry.register(OpenApplicationTool())
    registry.register(CloseApplicationTool())
    registry.register(ClickTool())
    registry.register(TypeTextTool())
    registry.register(HotkeyTool())
    registry.register(TakeScreenshotTool())

    # Phase 9 - System controls (implemented; needs the real OS APIs to act)
    from app.computer.system_tools import SetVolumeTool, SetBrightnessTool, LockComputerTool, MuteTool, GetLocationTool

    registry.register(SetVolumeTool())
    registry.register(SetBrightnessTool())
    registry.register(LockComputerTool())
    registry.register(MuteTool())
    registry.register(GetLocationTool())

    # Phase 5 - Browser (implemented; real Playwright automation)
    from app.browser.tools import (
        OpenBrowserTool,
        BrowserSearchTool,
        BrowserReadPageTool,
        BrowserClickTool,
        BrowserTypeTool,
    )

    registry.register(OpenBrowserTool())
    registry.register(BrowserSearchTool())
    registry.register(BrowserReadPageTool())
    registry.register(BrowserClickTool())
    registry.register(BrowserTypeTool())

    # Phase 6 - Coding agent (scaffolded)
    from app.coding.tools import RunProjectTool, RunTestsTool, ReadTerminalOutputTool

    registry.register(RunProjectTool())
    registry.register(RunTestsTool())
    registry.register(ReadTerminalOutputTool())

    # Phase 7 - Document agent (implemented; real docx/xlsx/pptx/pdf manipulation)
    from app.documents.tools import (
        OpenDocxTool,
        EditDocxTool,
        CreateReportTool,
        SummarizePdfTool,
        ExcelCalculateTotalsTool,
        CreatePptxFromReportTool,
    )

    registry.register(OpenDocxTool())
    registry.register(EditDocxTool())
    registry.register(CreateReportTool())
    registry.register(SummarizePdfTool())
    registry.register(ExcelCalculateTotalsTool())
    registry.register(CreatePptxFromReportTool())

    # Phase 11 - Job assistant (implemented)
    from app.jobs.tools import (
        AnalyzeJobTool,
        ExtractEmailsTool,
        GetProfileTool,
        PrepareApplicationTool,
        SearchJobsNearbyTool,
        SearchJobsTool,
        SubmitApplicationTool,
        UpdateProfileTool,
    )

    for tool_cls in (SearchJobsTool, SearchJobsNearbyTool, AnalyzeJobTool, UpdateProfileTool, GetProfileTool, PrepareApplicationTool, SubmitApplicationTool, ExtractEmailsTool):
        registry.register(tool_cls())

    # Phase 4 - Screen vision (implemented)
    from app.vision.tools import ScreenLookTool, ScreenReadTextTool

    registry.register(ScreenLookTool())
    registry.register(ScreenReadTextTool())

    return registry
