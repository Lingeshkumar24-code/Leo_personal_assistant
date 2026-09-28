"""
Phase 8 - File System Agent (implemented).

Cross-platform, safe subset of the spec's §13 requirements: search, read,
create folders, move, rename. Destructive/high-risk operations (bulk delete)
are intentionally left unimplemented here - deleting files safely needs a
confirmation UI flow beyond Phase 1's CLI, and the spec explicitly forbids
ever "blindly" deleting files.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.security.permissions import PermissionLevel
from app.tools.base import Tool, ToolResult


class FindFilesTool(Tool):
    name = "filesystem.find"
    description = "Search for files by name pattern under a root directory."
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Directory to search under"},
            "pattern": {"type": "string", "description": "Glob pattern, e.g. '*.py' or '*resume*'"},
        },
        "required": ["root", "pattern"],
    }

    def run(self, root: str, pattern: str, **kwargs) -> ToolResult:
        root_path = Path(root).expanduser()
        if not root_path.exists():
            return ToolResult(success=False, error=f"Root path does not exist: {root_path}")
        matches = [str(p) for p in root_path.rglob(pattern) if p.is_file()]
        return ToolResult(
            success=True,
            data={"matches": matches, "count": len(matches)},
            verification=f"Searched {root_path} recursively for pattern '{pattern}'.",
        )


class ReadFileTool(Tool):
    name = "filesystem.read"
    description = "Read the text contents of a file."
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def run(self, path: str, max_bytes: int = 200_000, **kwargs) -> ToolResult:
        file_path = Path(path).expanduser()
        if not file_path.exists():
            return ToolResult(success=False, error=f"File does not exist: {file_path}")
        if not file_path.is_file():
            return ToolResult(success=False, error=f"Not a file: {file_path}")
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")[:max_bytes]
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not read file: {e}")
        return ToolResult(success=True, data={"content": content, "path": str(file_path)})


class CreateFolderTool(Tool):
    name = "filesystem.create_folder"
    description = "Create a new folder (including parent folders)."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def run(self, path: str, **kwargs) -> ToolResult:
        folder_path = Path(path).expanduser()
        try:
            folder_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not create folder: {e}")
        return ToolResult(
            success=True,
            data={"path": str(folder_path)},
            verification=f"Verified folder exists: {folder_path.exists()}",
        )

    def verify(self, result: ToolResult, **kwargs) -> ToolResult:
        if result.success:
            path = Path(result.data["path"])
            result.success = path.exists() and path.is_dir()
            if not result.success:
                result.error = "Folder creation reported success but folder is not present on disk."
        return result


class MoveFileTool(Tool):
    name = "filesystem.move"
    description = "Move a file or folder to a new location."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {"source": {"type": "string"}, "destination": {"type": "string"}},
        "required": ["source", "destination"],
    }

    def run(self, source: str, destination: str, **kwargs) -> ToolResult:
        src = Path(source).expanduser()
        dst = Path(destination).expanduser()
        if not src.exists():
            return ToolResult(success=False, error=f"Source does not exist: {src}")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Move failed: {e}")
        return ToolResult(success=True, data={"destination": str(dst)})

    def verify(self, result: ToolResult, **kwargs) -> ToolResult:
        if result.success:
            result.success = Path(result.data["destination"]).exists()
        return result


class RenameFileTool(Tool):
    name = "filesystem.rename"
    description = "Rename a file or folder in place."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "new_name": {"type": "string"}},
        "required": ["path", "new_name"],
    }

    def run(self, path: str, new_name: str, **kwargs) -> ToolResult:
        src = Path(path).expanduser()
        if not src.exists():
            return ToolResult(success=False, error=f"Path does not exist: {src}")
        dst = src.with_name(new_name)
        try:
            src.rename(dst)
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Rename failed: {e}")
        return ToolResult(success=True, data={"new_path": str(dst)})

    def verify(self, result: ToolResult, **kwargs) -> ToolResult:
        if result.success:
            result.success = Path(result.data["new_path"]).exists()
        return result


class DeleteFileTool(Tool):
    """
    HIGH_RISK: always requires confirmation. Files are moved to data/trash
    (recoverable), never permanently erased. Refuses system folders, drive
    roots, the home folder itself, and bulk deletes over MAX_ITEMS.
    """

    name = "filesystem.delete"
    description = "Delete files/folders (moved to LEO's recoverable trash). Requires user confirmation."
    permission_level = PermissionLevel.HIGH_RISK
    parameters_schema = {
        "type": "object",
        "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
        "required": ["paths"],
    }
    MAX_ITEMS = 20
    _PROTECTED_PARTS = {"windows", "system32", "program files", "program files (x86)", "programdata", "/etc", "/usr", "/bin", "/boot"}

    def _is_protected(self, p: Path) -> bool:
        rp = p.resolve()
        if rp == Path.home().resolve() or rp == Path(rp.anchor):
            return True
        lowered = str(rp).lower().replace("\\", "/")
        return any(part in lowered.split("/") or lowered.startswith(part) for part in self._PROTECTED_PARTS)

    def run(self, paths: list[str], **kwargs) -> ToolResult:
        from app.core.config import settings
        import time

        if len(paths) > self.MAX_ITEMS:
            return ToolResult(success=False, error=f"Refusing to delete {len(paths)} items at once (limit {self.MAX_ITEMS}).")
        trash = Path(settings.data_dir) / "trash" / time.strftime("%Y%m%d_%H%M%S")
        moved, problems = [], []
        for raw in paths:
            src = Path(raw).expanduser()
            if not src.exists():
                problems.append(f"{src} does not exist")
            elif self._is_protected(src):
                problems.append(f"{src} is protected and was not touched")
            else:
                trash.mkdir(parents=True, exist_ok=True)
                dst = trash / src.name
                shutil.move(str(src), str(dst))
                moved.append({"from": str(src), "trash": str(dst)})
        return ToolResult(
            success=bool(moved) and not problems,
            data={"moved_to_trash": moved, "problems": problems},
            error="; ".join(problems) or None,
            verification=f"Moved {len(moved)} item(s) to recoverable trash." if moved else None,
        )

    def verify(self, result: ToolResult, **kwargs) -> ToolResult:
        for item in result.data.get("moved_to_trash", []):
            if Path(item["from"]).exists() or not Path(item["trash"]).exists():
                result.success = False
                result.error = "Delete could not be verified."
        return result
