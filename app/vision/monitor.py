"""
SCREEN_MONITORING mode (spec §6): a background thread that, every few seconds,
captures the screen, skips it if unchanged, OCRs it LOCALLY and stores the
result as screen context. Nothing is uploaded while watching; a screenshot
only goes to the cloud when you ask a screen question (screen.look).
"""
from __future__ import annotations

import hashlib
import threading

from app.core import events
from app.memory.store import ShortTermMemory
from app.vision.screen import ScreenUnavailable, active_window_title, capture_screenshot, ocr_text


class ScreenMonitor:
    def __init__(self, short_term: ShortTermMemory, interval: float = 5.0):
        self.short_term = short_term
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_hash = ""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="leo-screen-monitor")
        self._thread.start()
        events.update(screen="watching")

    def stop(self) -> None:
        self._stop.set()
        events.update(screen="on_demand")

    def tick(self) -> bool:
        """One observation. Returns True if the screen changed."""
        path = capture_screenshot(max_width=1000)
        with open(path, "rb") as f:
            digest = hashlib.md5(f.read()).hexdigest()  # noqa: S324 - change detection only
        if digest == self._last_hash:
            return False
        self._last_hash = digest
        self.short_term.screen_context = {
            "active_window": active_window_title(),
            "visible_text": ocr_text(path)[:2500],
        }
        return True

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.tick()
            except ScreenUnavailable as e:
                events.add_log("error", f"Screen watch stopped: {e}")
                events.update(screen="off")
                return
            except Exception:  # noqa: BLE001
                continue
