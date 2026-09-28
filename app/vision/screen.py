"""
Phase 4 - Screen vision (implemented).

capture -> downscale -> OCR (if available) -> vision model.
Privacy: screenshots are sent to your configured cloud AI provider only when
you ask a screen question (or while screen monitoring is switched on).
Requires SCREEN_CAPTURE_ENABLED=true in .env.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from app.core.config import settings


class ScreenUnavailable(RuntimeError):
    pass


def capture_screenshot(output_path: str | None = None, max_width: int = 1600) -> str:
    """Capture the full screen, downscale it, save as PNG, return the path."""
    if not settings.screen_capture_enabled:
        raise ScreenUnavailable("Screen capture is off. Set SCREEN_CAPTURE_ENABLED=true in .env to allow it.")
    try:
        from PIL import ImageGrab

        image = ImageGrab.grab(all_screens=True)
    except Exception as e:  # noqa: BLE001
        try:
            import pyautogui

            image = pyautogui.screenshot()
        except Exception as e2:  # noqa: BLE001
            raise ScreenUnavailable(f"Could not capture the screen (needs a real display): {e}; {e2}") from e2
    if image.width > max_width:
        ratio = max_width / image.width
        image = image.resize((max_width, int(image.height * ratio)))
    path = output_path or str(Path(tempfile.gettempdir()) / f"leo_screen_{int(time.time())}.png")
    image.save(path)
    return path


def ocr_text(image_path: str) -> str:
    """OCR via pytesseract if installed; returns '' if OCR isn't available."""
    try:
        import pytesseract
        from PIL import Image

        return pytesseract.image_to_string(Image.open(image_path)).strip()
    except Exception:  # noqa: BLE001
        return ""


def active_window_title() -> str:
    try:
        import pygetwindow as gw

        win = gw.getActiveWindow()
        return win.title if win else ""
    except Exception:  # noqa: BLE001
        return ""
