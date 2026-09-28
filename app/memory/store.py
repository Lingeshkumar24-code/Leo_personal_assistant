"""
Phase 10 - Memory (implemented).

SHORT TERM: current conversation / task / app / screen context - kept only
            in-process for the life of the running session.
LONG TERM:  user preferences, common projects, task history - persisted to
            data/memory.json so it survives restarts. Fully editable and
            deletable by the user (§16 of the spec).
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings

_LOCK = threading.Lock()


@dataclass
class ShortTermMemory:
    conversation: list[dict[str, str]] = field(default_factory=list)
    current_task: str | None = None
    current_application: str | None = None
    screen_context: dict[str, Any] = field(default_factory=dict)

    def add_turn(self, role: str, content: str) -> None:
        self.conversation.append({"role": role, "content": content})

    def recent(self, n: int = 10) -> list[dict[str, str]]:
        return self.conversation[-n:]

    def clear(self) -> None:
        self.conversation.clear()
        self.current_task = None
        self.current_application = None
        self.screen_context = {}


class LongTermMemory:
    """Simple, transparent JSON-file key/value + history store."""

    def __init__(self, path: Path | None = None):
        self.path = path or (Path(settings.data_dir) / "memory.json")
        if not self.path.exists():
            self._write({"preferences": {}, "projects": {}, "task_history": []})

    def _read(self) -> dict[str, Any]:
        with _LOCK:
            if not self.path.exists():
                return {"preferences": {}, "projects": {}, "task_history": []}
            return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        with _LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- preferences (freeform key/value user facts) ----
    def remember(self, key: str, value: Any) -> None:
        data = self._read()
        data["preferences"][key] = value
        self._write(data)

    def recall(self, key: str) -> Any:
        return self._read()["preferences"].get(key)

    def all_preferences(self) -> dict[str, Any]:
        return self._read()["preferences"]

    def forget(self, key: str) -> bool:
        data = self._read()
        existed = key in data["preferences"]
        data["preferences"].pop(key, None)
        self._write(data)
        return existed

    def clear_all(self) -> None:
        self._write({"preferences": {}, "projects": {}, "task_history": []})

    # ---- named projects, e.g. "F1 project" -> path ----
    def set_project(self, name: str, path: str) -> None:
        data = self._read()
        data["projects"][name.lower()] = path
        self._write(data)

    def get_project(self, name: str) -> str | None:
        return self._read()["projects"].get(name.lower())

    # ---- task history ----
    def log_task(self, task: str, result: str) -> None:
        data = self._read()
        data["task_history"].append(
            {
                "task": task,
                "result": result,
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        data["task_history"] = data["task_history"][-200:]  # cap history size
        self._write(data)

    def recent_tasks(self, n: int = 10) -> list[dict[str, str]]:
        return self._read()["task_history"][-n:]


long_term_memory = LongTermMemory()
