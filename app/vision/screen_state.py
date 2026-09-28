"""
Phase 4 - Vision System (§6 of the spec). Scaffolded, not implemented.

Defines the structured screen-state representation the spec asks for, so
Phase 3/5/6 tools can already be written against a stable interface. Real
implementation: mss/Pillow for screenshot capture, pytesseract/easyocr for
OCR, and an accessibility-tree or vision-model pass for UI element detection.
Screen capture must respect SCREEN_CAPTURE_ENABLED and only run on-demand or
in explicit monitoring modes — never continuous blind capture (§6, §31).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ScreenMode(str, Enum):
    OFF = "SCREEN_OFF"
    ON_DEMAND = "SCREEN_ON_DEMAND"
    MONITORING = "SCREEN_MONITORING"
    AGENT_MODE = "SCREEN_AGENT_MODE"


@dataclass
class ScreenState:
    current_application: str | None = None
    active_window: str | None = None
    visible_text: str = ""
    detected_buttons: list[str] = field(default_factory=list)
    detected_fields: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    browser_url: str | None = None
    cursor_state: str | None = None


def capture_screen_state(mode: ScreenMode = ScreenMode.ON_DEMAND) -> ScreenState:
    """
    Not implemented yet. Raises so callers never silently receive a fake,
    empty screen state and mistake it for "nothing visible."
    """
    raise NotImplementedError(
        "Screen capture/OCR/vision pipeline is not implemented yet (Phase 4). "
        "See README.md 'Project status'."
    )
