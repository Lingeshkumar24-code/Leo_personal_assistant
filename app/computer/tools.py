"""
Phase 3 - Computer Control (implemented).

Real desktop automation via pyautogui (mouse/keyboard, cross-platform) and
subprocess/os for launching applications. On Windows, application launch
also tries the Start Menu search via `os.startfile` / `start` for apps that
aren't on PATH, which is the most reliable way to open GUI apps by name.

Honesty note: this code is real and follows each library's documented API
exactly as it would run on a Windows desktop with a screen attached. It
could not be exercised end-to-end in the build sandbox because that
sandbox has no display (Xvfb/X server) and is not Windows - pyautogui and
pywinauto both require a real display/window manager to do anything. Every
method below fails with a clear, honest error if the required display or
platform isn't present, rather than pretending to click or type.
"""
from __future__ import annotations

import platform
import subprocess
import shutil
import time

from app.security.permissions import PermissionLevel
from app.tools.base import Tool, ToolResult

IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


def _require_pyautogui():
    try:
        import pyautogui  # noqa: F401

        return pyautogui
    except Exception as e:  # noqa: BLE001 - covers ImportError and "no display" errors alike
        raise RuntimeError(
            f"pyautogui is unavailable here ({e}). It needs a real display; "
            "install with 'pip install pyautogui' and run on a machine with a screen."
        ) from e


class OpenApplicationTool(Tool):
    name = "computer.open_application"
    description = "Launch a desktop application by name (e.g. 'notepad', 'chrome')."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {"type": "object", "properties": {"app_name": {"type": "string"}}, "required": ["app_name"]}

    # Common Windows app name -> launch command aliases
    _WINDOWS_ALIASES = {
        "notepad": "notepad.exe",
        "chrome": "chrome.exe",
        "google chrome": "chrome.exe",
        "word": "winword.exe",
        "excel": "excel.exe",
        "powerpoint": "powerpnt.exe",
        "calculator": "calc.exe",
        "task manager": "taskmgr.exe",
        "settings": "start ms-settings:",
        "explorer": "explorer.exe",
        "vs code": "code",
        "visual studio code": "code",
        "vscode": "code",
    }

    def run(self, app_name: str, **kwargs) -> ToolResult:
        name_lower = app_name.strip().lower()
        try:
            if IS_WINDOWS:
                command = self._WINDOWS_ALIASES.get(name_lower, app_name)
                if command.startswith("start "):
                    subprocess.Popen(command, shell=True)
                else:
                    subprocess.Popen(["cmd", "/c", "start", "", command], shell=False)
            elif IS_MAC:
                subprocess.Popen(["open", "-a", app_name])
            elif IS_LINUX:
                resolved = shutil.which(name_lower.replace(" ", "-")) or shutil.which(name_lower)
                if not resolved:
                    return ToolResult(success=False, error=f"Could not find an executable for '{app_name}' on PATH.")
                subprocess.Popen([resolved])
            else:
                return ToolResult(success=False, error=f"Unsupported platform: {platform.system()}")
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Failed to launch '{app_name}': {e}")

        time.sleep(1.0)  # give the OS a moment before verification
        return ToolResult(success=True, data={"app_name": app_name}, verification=f"Launch command issued for '{app_name}'.")

    def verify(self, result: ToolResult, app_name: str = "", **kwargs) -> ToolResult:
        # Best-effort verification via psutil if available; otherwise trust the launch call.
        if not result.success:
            return result
        try:
            import psutil

            target = app_name.lower().split(".")[0]
            running = any(target in (p.name() or "").lower() for p in psutil.process_iter(["name"]))
            if not running:
                result.verification = f"Launch command for '{app_name}' issued, but no matching process was detected yet."
            else:
                result.verification = f"Confirmed a process matching '{app_name}' is running."
        except ImportError:
            result.verification = "psutil not installed; process-level verification skipped (pip install psutil for this)."
        return result


class CloseApplicationTool(Tool):
    name = "computer.close_application"
    description = "Close a running application by name."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {"type": "object", "properties": {"app_name": {"type": "string"}}, "required": ["app_name"]}

    def run(self, app_name: str, **kwargs) -> ToolResult:
        try:
            import psutil
        except ImportError:
            return ToolResult(success=False, error="psutil is not installed. pip install psutil")

        target = app_name.lower().replace(".exe", "")
        closed = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if target in (proc.info["name"] or "").lower():
                    proc.terminate()
                    closed.append(proc.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not closed:
            return ToolResult(success=False, error=f"No running process matching '{app_name}' was found.")
        return ToolResult(success=True, data={"closed_processes": closed})


class ClickTool(Tool):
    name = "computer.click"
    description = "Click at screen coordinates."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string"}},
        "required": ["x", "y"],
    }

    def run(self, x: int, y: int, button: str = "left", **kwargs) -> ToolResult:
        try:
            pyautogui = _require_pyautogui()
            pyautogui.click(x=x, y=y, button=button)
        except RuntimeError as e:
            return ToolResult(success=False, error=str(e))
        return ToolResult(success=True, data={"x": x, "y": y, "button": button})


class TypeTextTool(Tool):
    name = "computer.type_text"
    description = "Type text into the currently focused field."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

    def run(self, text: str, interval: float = 0.02, **kwargs) -> ToolResult:
        try:
            pyautogui = _require_pyautogui()
            pyautogui.write(text, interval=interval)
        except RuntimeError as e:
            return ToolResult(success=False, error=str(e))
        return ToolResult(success=True, data={"characters_typed": len(text)})


class HotkeyTool(Tool):
    name = "computer.hotkey"
    description = "Press a keyboard shortcut, e.g. keys=['ctrl','s']."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {"type": "object", "properties": {"keys": {"type": "array", "items": {"type": "string"}}}, "required": ["keys"]}

    def run(self, keys: list[str], **kwargs) -> ToolResult:
        try:
            pyautogui = _require_pyautogui()
            pyautogui.hotkey(*keys)
        except RuntimeError as e:
            return ToolResult(success=False, error=str(e))
        return ToolResult(success=True, data={"keys": keys})


class TakeScreenshotTool(Tool):
    name = "computer.take_screenshot"
    description = "Capture a screenshot and save it to a path."
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {"type": "object", "properties": {"output_path": {"type": "string"}}, "required": ["output_path"]}

    def run(self, output_path: str, **kwargs) -> ToolResult:
        try:
            pyautogui = _require_pyautogui()
            image = pyautogui.screenshot()
            image.save(output_path)
        except RuntimeError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not save screenshot: {e}")
        return ToolResult(success=True, data={"output_path": output_path})
