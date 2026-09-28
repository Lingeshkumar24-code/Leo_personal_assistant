"""
Permission system (§18 of the spec).

Four levels:
  OBSERVE     - read screen/files, search, explain
  NORMAL      - open apps, type, click, navigate, run tests
  PRIVILEGED  - install packages, git push, external submissions
  HIGH_RISK   - delete files, shutdown, financial/account actions

The LLM can never silently bypass this - every Tool declares its
`permission_level`, and the orchestrator checks it against the current mode
and user configuration before running the tool.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
import json

from app.core.config import settings


class PermissionLevel(IntEnum):
    OBSERVE = 0
    NORMAL = 1
    PRIVILEGED = 2
    HIGH_RISK = 3


class OperatingMode:
    MANUAL = "manual"          # LEO asks before NORMAL and above
    ASSISTED = "assisted"      # LEO auto-runs NORMAL, asks for PRIVILEGED/HIGH_RISK
    AUTONOMOUS = "autonomous"  # LEO auto-runs NORMAL+PRIVILEGED, still asks for HIGH_RISK


_AUTO_THRESHOLD = {
    OperatingMode.MANUAL: PermissionLevel.OBSERVE,
    OperatingMode.ASSISTED: PermissionLevel.NORMAL,
    OperatingMode.AUTONOMOUS: PermissionLevel.PRIVILEGED,
}

# HIGH_RISK always requires confirmation, no matter the mode. This is a hard
# floor that cannot be configured away, per §18/§20 of the spec.
_HARD_CONFIRM_FLOOR = PermissionLevel.HIGH_RISK


@dataclass
class PermissionDecision:
    allowed: bool
    requires_confirmation: bool
    reason: str = ""


@dataclass
class PermissionManager:
    mode: str = field(default_factory=lambda: settings.mode)
    _audit_log_path: Path = field(default_factory=lambda: Path(settings.log_dir) / "audit.log")

    def set_mode(self, mode: str) -> None:
        if mode not in {OperatingMode.MANUAL, OperatingMode.ASSISTED, OperatingMode.AUTONOMOUS}:
            raise ValueError(f"Unknown mode '{mode}'")
        self.mode = mode

    def evaluate(self, tool_name: str, level: PermissionLevel) -> PermissionDecision:
        auto_threshold = _AUTO_THRESHOLD[self.mode]
        if level >= _HARD_CONFIRM_FLOOR:
            return PermissionDecision(
                allowed=True,
                requires_confirmation=True,
                reason=f"{tool_name} is HIGH_RISK; confirmation is always required.",
            )
        if level <= auto_threshold:
            return PermissionDecision(allowed=True, requires_confirmation=False)
        return PermissionDecision(
            allowed=True,
            requires_confirmation=True,
            reason=f"{tool_name} is {level.name}, above the auto-run threshold for mode '{self.mode}'.",
        )

    def audit(self, entry: dict) -> None:
        self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._audit_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")


permission_manager = PermissionManager()
