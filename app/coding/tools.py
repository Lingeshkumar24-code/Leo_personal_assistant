"""
Phase 6 - Coding Agent (implemented).

Real project detection + subprocess execution, with output captured for the
autonomous debugging loop in app/agents/task_manager.py. No GUI automation -
this runs actual shell commands and reads their real stdout/stderr.
"""
from __future__ import annotations

import subprocess
import threading
import uuid
from pathlib import Path

from app.security.permissions import PermissionLevel
from app.tools.base import Tool, ToolResult

_SESSIONS: dict[str, subprocess.Popen] = {}
_SESSIONS_LOCK = threading.Lock()

_PROJECT_SIGNATURES = [
    ("package.json", ["npm", "start"]),
    ("pyproject.toml", ["python", "-m", "app"]),
    ("manage.py", ["python", "manage.py", "runserver"]),
    ("requirements.txt", ["python", "main.py"]),
    ("Cargo.toml", ["cargo", "run"]),
    ("go.mod", ["go", "run", "."]),
]

_TEST_SIGNATURES = [
    ("pyproject.toml", ["pytest"]),
    ("requirements.txt", ["pytest"]),
    ("package.json", ["npm", "test"]),
    ("Cargo.toml", ["cargo", "test"]),
    ("go.mod", ["go", "test", "./..."]),
]


def _detect_command(project_path: Path, signatures) -> list[str] | None:
    for filename, command in signatures:
        if (project_path / filename).exists():
            return command
    return None


class RunProjectTool(Tool):
    name = "coding.run_project"
    description = "Detect the project type in a directory and start it as a background process."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {"type": "object", "properties": {"project_path": {"type": "string"}}, "required": ["project_path"]}

    def run(self, project_path: str, **kwargs) -> ToolResult:
        path = Path(project_path).expanduser()
        if not path.exists() or not path.is_dir():
            return ToolResult(success=False, error=f"Project path does not exist or is not a directory: {path}")

        command = _detect_command(path, _PROJECT_SIGNATURES)
        if command is None:
            return ToolResult(
                success=False,
                error=(
                    f"Could not detect a known project type in {path}. "
                    "Looked for package.json, pyproject.toml, manage.py, requirements.txt, Cargo.toml, go.mod."
                ),
            )

        try:
            process = subprocess.Popen(
                command,
                cwd=str(path),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as e:
            return ToolResult(success=False, error=f"Command not found ({' '.join(command)}): {e}")
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not start project: {e}")

        session_id = str(uuid.uuid4())[:8]
        with _SESSIONS_LOCK:
            _SESSIONS[session_id] = process

        return ToolResult(
            success=True,
            data={"session_id": session_id, "command": command, "pid": process.pid},
            verification=f"Started '{' '.join(command)}' (pid={process.pid}); read output with coding.read_terminal_output.",
        )


class RunTestsTool(Tool):
    name = "coding.run_tests"
    description = "Run the project's test suite (blocking) and return pass/fail results with output."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {"type": "object", "properties": {"project_path": {"type": "string"}}, "required": ["project_path"]}

    def run(self, project_path: str, timeout: int = 120, **kwargs) -> ToolResult:
        path = Path(project_path).expanduser()
        if not path.exists() or not path.is_dir():
            return ToolResult(success=False, error=f"Project path does not exist or is not a directory: {path}")

        command = _detect_command(path, _TEST_SIGNATURES)
        if command is None:
            return ToolResult(success=False, error=f"Could not detect a test command for {path}.")

        try:
            result = subprocess.run(
                command, cwd=str(path), capture_output=True, text=True, timeout=timeout
            )
        except FileNotFoundError as e:
            return ToolResult(success=False, error=f"Test command not found ({' '.join(command)}): {e}")
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error=f"Tests timed out after {timeout}s.")

        output = (result.stdout or "") + (result.stderr or "")
        passed = result.returncode == 0
        return ToolResult(
            success=passed,
            data={"command": command, "returncode": result.returncode, "output": output[-8000:]},
            verification=f"Exit code {result.returncode} ({'passed' if passed else 'failed'}).",
            error=None if passed else f"Tests failed (exit code {result.returncode}). See output.",
        )


class ReadTerminalOutputTool(Tool):
    name = "coding.read_terminal_output"
    description = "Read the output collected so far from a running process/session started by coding.run_project."
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {"type": "object", "properties": {"session_id": {"type": "string"}}, "required": ["session_id"]}

    def run(self, session_id: str, max_lines: int = 200, **kwargs) -> ToolResult:
        with _SESSIONS_LOCK:
            process = _SESSIONS.get(session_id)
        if process is None:
            return ToolResult(success=False, error=f"No session found with id '{session_id}'.")

        lines = []
        if process.stdout is not None:
            import select

            while len(lines) < max_lines:
                ready, _, _ = select.select([process.stdout], [], [], 0.2)
                if not ready:
                    break
                line = process.stdout.readline()
                if not line:
                    break
                lines.append(line.rstrip("\n"))

        return ToolResult(
            success=True,
            data={
                "session_id": session_id,
                "running": process.poll() is None,
                "returncode": process.poll(),
                "output": "\n".join(lines),
            },
        )
