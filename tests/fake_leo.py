"""A Leo wired to a deterministic planner (no API key) but the REAL tools/permissions/task manager."""
from app.agents.planner import Plan, PlannedStep
from app.agents.task_manager import TaskManager
from app.core.orchestrator import Leo
from app.memory.store import ShortTermMemory
from app.tools.registry import build_default_registry


class ScriptedPlanner:
    def plan(self, text, conversation=None):
        low = text.lower()
        if low.startswith("remember "):
            return Plan(steps=[PlannedStep("memory.remember", {"key": "note", "value": text[9:]})])
        if low.startswith("delete "):
            return Plan(steps=[PlannedStep("filesystem.delete", {"paths": [text[7:].strip()]})])
        return Plan(steps=[], direct_response=f"You said: {text}")


class FakeProvider:
    name = "fake"


def make_leo() -> Leo:
    registry = build_default_registry()
    return Leo(provider=FakeProvider(), registry=registry, planner=ScriptedPlanner(),
               task_manager=TaskManager(registry=registry), short_term=ShortTermMemory())
