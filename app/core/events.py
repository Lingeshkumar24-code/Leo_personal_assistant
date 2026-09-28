"""
Live assistant state shared with the UI (spec: task status, activity log, progress).
log_stage() feeds this, so the UI shows what LEO is really doing, not a mock.
"""
from __future__ import annotations

import threading
import time
from typing import Any

_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "state": "idle",          # idle | listening | thinking | executing | speaking | success | error
    "task": "",
    "step": "",
    "progress": 0.0,
    "steps_total": 0,
    "steps_done": 0,
    "log": [],
    "mic": False,
    "screen": "off",          # off | on_demand | watching
    "mode": "manual",
    "provider": "",
    "pending_confirmation": None,
    "reply": "",
    "level": 0.0,             # voice amplitude 0..1 for the orb
}


def snapshot() -> dict[str, Any]:
    with _LOCK:
        return {**_STATE, "log": list(_STATE["log"][-60:]), "time": time.time()}


def update(**kwargs: Any) -> None:
    with _LOCK:
        _STATE.update(kwargs)


def add_log(kind: str, text: str) -> None:
    with _LOCK:
        _STATE["log"].append({"t": time.strftime("%H:%M:%S"), "kind": kind, "text": text})
        _STATE["log"] = _STATE["log"][-200:]


def on_stage(stage: str, payload: dict[str, Any]) -> None:
    """Translate pipeline log stages into UI state."""
    if stage == "INTENT":
        update(state="thinking", task=str(payload.get("instruction", "")), step="Understanding request",
               progress=0.05, steps_done=0, steps_total=0, reply="")
        add_log("intent", f"You: {payload.get('instruction', '')}")
    elif stage == "PLAN":
        steps = payload.get("steps", [])
        if steps:
            update(steps_total=len(steps), state="executing", step="Planned " + ", ".join(s["tool"] for s in steps)[:80], progress=0.15)
            add_log("plan", "Plan: " + " → ".join(s["tool"] for s in steps))
        else:
            add_log("plan", "Answering directly")
    elif stage == "ACTION":
        update(state="executing", step=f"Running {payload.get('tool')}")
        add_log("action", f"Running {payload.get('tool')}")
    elif stage == "OBSERVATION_VERIFICATION":
        with _LOCK:
            _STATE["steps_done"] += 1
            total = max(_STATE["steps_total"], 1)
            _STATE["progress"] = min(0.15 + 0.85 * _STATE["steps_done"] / total, 0.99)
        ok = payload.get("success")
        add_log("ok" if ok else "error", f"{payload.get('tool')}: " + str(payload.get("verification") or payload.get("error") or ""))
    elif stage == "EMERGENCY_STOP":
        update(state="error", step="Emergency stop")
        add_log("error", "Emergency stop")
