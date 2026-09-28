"""
The full pipeline (see README / spec §2):

VOICE -> STT -> INTENT -> PLANNER -> TOOL SELECTION -> EXECUTION ->
OBSERVATION -> VERIFICATION -> MEMORY -> RESPONSE

Phase 1 drives this via typed text (voice is Phase 2), but every other stage
is real: intent goes through the actual planner, execution runs actual
tools, and everything is logged and remembered.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.agents.planner import Planner
from app.agents.task_manager import TaskManager, TaskOutcome
from app.core.config import settings
from app.core.logger import log_stage
from app.memory.store import ShortTermMemory, long_term_memory
from app.providers.base import AIProvider
from app.providers.factory import get_provider
from app.security.permissions import permission_manager
from app.tools.registry import ToolRegistry, build_default_registry


@dataclass
class Leo:
    provider: AIProvider
    registry: ToolRegistry
    planner: Planner
    task_manager: TaskManager
    short_term: ShortTermMemory

    @classmethod
    def bootstrap(cls, confirm_callback: Callable[[str, str], bool] | None = None) -> "Leo":
        problems = settings.validate_for_provider()
        if problems:
            raise RuntimeError(
                "LEO configuration is incomplete:\n- " + "\n- ".join(problems) + "\n\nEdit your .env file."
            )
        permission_manager.set_mode(settings.mode)
        provider = get_provider()
        registry = build_default_registry()
        planner = Planner(provider=provider, registry=registry)
        task_manager = TaskManager(registry=registry, confirm_callback=confirm_callback)
        return cls(
            provider=provider,
            registry=registry,
            planner=planner,
            task_manager=task_manager,
            short_term=ShortTermMemory(),
        )

    def handle(self, user_instruction: str) -> TaskOutcome:
        log_stage("INTENT", {"instruction": user_instruction})
        self.short_term.add_turn("user", user_instruction)

        planner_input = user_instruction
        ctx = self.short_term.screen_context
        if ctx:  # locally OCR'd by the screen monitor; never uploaded as an image
            planner_input += (f"\n\n[Screen context - active window: {ctx.get('active_window', '?')}; "
                              f"visible text: {ctx.get('visible_text', '')[:1500]}]")
        plan = self.planner.plan(planner_input, conversation=self.short_term.recent()[:-1])
        log_stage(
            "PLAN",
            {
                "steps": [{"tool": s.tool_name, "arguments": s.arguments} for s in plan.steps],
                "direct_response": plan.direct_response if not plan.steps else "",
            },
        )

        outcome = self.task_manager.execute(plan, user_instruction)
        self.short_term.add_turn("assistant", outcome.summary())
        return outcome
