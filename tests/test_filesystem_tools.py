import json
from pathlib import Path

from app.filesystem.tools import (
    CreateFolderTool,
    FindFilesTool,
    MoveFileTool,
    ReadFileTool,
    RenameFileTool,
)


def test_create_folder_and_verify(tmp_path):
    tool = CreateFolderTool()
    target = tmp_path / "new_folder"
    result = tool.run(path=str(target))
    result = tool.verify(result, path=str(target))
    assert result.success
    assert target.exists()


def test_find_files(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.py").write_text("print(1)")
    tool = FindFilesTool()
    result = tool.run(root=str(tmp_path), pattern="*.py")
    assert result.success
    assert result.data["count"] == 1
    assert result.data["matches"][0].endswith("b.py")


def test_read_file_missing_returns_failure(tmp_path):
    tool = ReadFileTool()
    result = tool.run(path=str(tmp_path / "does_not_exist.txt"))
    assert not result.success
    assert "does not exist" in result.error


def test_move_file(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("data")
    dst = tmp_path / "sub" / "dst.txt"
    tool = MoveFileTool()
    result = tool.run(source=str(src), destination=str(dst))
    result = tool.verify(result)
    assert result.success
    assert dst.exists()
    assert not src.exists()


def test_rename_file(tmp_path):
    src = tmp_path / "old.txt"
    src.write_text("data")
    tool = RenameFileTool()
    result = tool.run(path=str(src), new_name="new.txt")
    result = tool.verify(result)
    assert result.success
    assert (tmp_path / "new.txt").exists()
