"""
Task Manager (§17, §19 of the spec).

Executes a Plan step by step:
  ACTION -> OBSERVATION -> VERIFICATION -> RESULT
gated by the permission system (§18), with everything logged (§26), and
bounded retries (§11 autonomous debugging loop is a specialization of this
same shape, added properly once Phase 6 lands).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app.agents.planner import Plan
from app.core.logger import log_stage
from app.core.stop import stop_requested
from app.memory.store import long_term_memory
from app.security.permissions import PermissionLevel, PermissionManager, permission_manager
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry

MAX_RETRIES_PER_STEP = 2


@dataclass
class StepOutcome:
    tool_name: str
    arguments: dict
    result: ToolResult
    confirmed: bool


@dataclass
class TaskOutcome:
    instruction: str
    steps: list[StepOutcome] = field(default_factory=list)
    direct_response: str = ""

    @property
    def success(self) -> bool:
        if not self.steps:
            return True  # direct response, no tool needed
        return all(s.result.success for s in self.steps)

    def summary(self) -> str:
        if not self.steps:
            return self.direct_response
        lines = []
        for s in self.steps:
            status = "✅" if s.result.success else "❌"
            detail = s.result.verification or s.result.error or ""
            lines.append(f"{status} {s.tool_name}: {detail}".strip())
        return "\n".join(lines)


class TaskManager:
    def __init__(
        self,
        registry: ToolRegistry,
        permissions: PermissionManager = permission_manager,
        confirm_callback: Callable[[str, str], bool] | None = None,
    ):
        self.registry = registry
        self.permissions = permissions
        # confirm_callback(tool_name, reason) -> bool ; defaults to auto-deny for safety
        self.confirm_callback = confirm_callback or (lambda tool, reason: False)

    def execute(self, plan: Plan, instruction: str) -> TaskOutcome:
        outcome = TaskOutcome(instruction=instruction, direct_response=plan.direct_response)

        for step in plan.steps:
            if stop_requested():
                log_stage("EMERGENCY_STOP", {"instruction": instruction})
                outcome.direct_response = "Stopped."
                break
            tool = self.registry.get(step.tool_name)
            if tool is None:
                result = ToolResult(success=False, error=f"Unknown tool: {step.tool_name}")
                outcome.steps.append(StepOutcome(step.tool_name, step.arguments, result, confirmed=False))
                continue

            decision = self.permissions.evaluate(tool.name, tool.permission_level)
            confirmed = True
            if decision.requires_confirmation:
                confirmed = self.confirm_callback(tool.name, decision.reason)
                self.permissions.audit(
                    {
                        "event": "permission_check",
                        "tool": tool.name,
                        "level": tool.permission_level.name,
                        "confirmed": confirmed,
                        "reason": decision.reason,
                    }
                )
                if not confirmed:
                    result = ToolResult(success=False, error="User did not confirm this action.")
                    outcome.steps.append(StepOutcome(tool.name, step.arguments, result, confirmed=False))
                    log_stage("ACTION_SKIPPED", {"tool": tool.name, "reason": "not confirmed"})
                    continue

            log_stage("ACTION", {"tool": tool.name, "arguments": step.arguments})

            result = self._run_with_retries(tool, step.arguments)

            log_stage(
                "OBSERVATION_VERIFICATION",
                {"tool": tool.name, "success": result.success, "verification": result.verification, "error": result.error},
            )

            outcome.steps.append(StepOutcome(tool.name, step.arguments, result, confirmed=confirmed))
            long_term_memory.log_task(f"{tool.name}({step.arguments})", "success" if result.success else f"failed: {result.error}")

        log_stage("RESPONSE", {"instruction": instruction, "success": outcome.success})
        return outcome

    def _run_with_retries(self, tool, arguments: dict) -> ToolResult:
        last_result = None
        for attempt in range(1, MAX_RETRIES_PER_STEP + 2):
            try:
                result = tool.run(**arguments)
                result = tool.verify(result, **arguments)
            except NotImplementedError as e:
                return ToolResult(success=False, error=str(e))
            except Exception as e:  # noqa: BLE001 - tool failures must never crash LEO (§27)
                result = ToolResult(success=False, error=f"Tool raised an exception: {e}")

            # Only read-only tools are retried: re-running a click/type/delete could act twice.
            if result.success or attempt > MAX_RETRIES_PER_STEP or tool.permission_level != PermissionLevel.OBSERVE:
                return result
            last_result = result
            log_stage(
                "RETRY",
                {"tool": tool.name, "attempt": attempt, "previous_error": result.error},
            )
        return last_result
