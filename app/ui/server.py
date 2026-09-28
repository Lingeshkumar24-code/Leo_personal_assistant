"""
LEO desktop UI server (Phase 13 backend).

Serves the 3D interface and a small JSON API on 127.0.0.1 only.
Security: every /api call needs the per-session token (passed in the URL LEO opens),
and Host/Origin are checked, so a random website in your browser cannot drive your PC.
"""
from __future__ import annotations

import json
import mimetypes
import secrets
import shutil
import subprocess
import sys
import threading
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from app.core import events
from app.core.config import settings
from app.core.orchestrator import Leo
from app.core.stop import clear_stop, install_hotkey, request_stop
from app.jobs.profile import UserProfile, profile_store
from app.memory.store import long_term_memory
from app.vision.monitor import ScreenMonitor

UI_DIR = Path(__file__).resolve().parents[2] / "assets" / "ui"
CONFIRM_TIMEOUT = 120


class Runtime:
    def __init__(self, leo: Leo, token: str):
        self.leo = leo
        self.token = token
        self.busy = threading.Lock()
        self.monitor = ScreenMonitor(leo.short_term)
        self.voice_thread: threading.Thread | None = None
        self.voice_on = False
        self._confirm_event = threading.Event()
        self._confirm_result = False
        leo.task_manager.confirm_callback = self.confirm

    # --- confirmations go through the UI modal ---
    def confirm(self, tool: str, reason: str) -> bool:
        self._confirm_event.clear()
        self._confirm_result = False
        events.update(pending_confirmation={"tool": tool, "reason": reason}, state="thinking", step=f"Waiting for your approval: {tool}")
        events.add_log("action", f"Approval needed: {tool}")
        self._confirm_event.wait(CONFIRM_TIMEOUT)
        events.update(pending_confirmation=None)
        return self._confirm_result

    def answer_confirmation(self, approve: bool) -> None:
        self._confirm_result = approve
        self._confirm_event.set()

    # --- commands ---
    def submit(self, text: str) -> bool:
        if not self.busy.acquire(blocking=False):
            return False
        threading.Thread(target=self._run, args=(text,), daemon=True, name="leo-task").start()
        return True

    def _run(self, text: str) -> None:
        try:
            clear_stop()
            outcome = self.leo.handle(text)
            events.update(state="success" if outcome.success else "error", progress=1.0,
                          step="Done" if outcome.success else "Finished with problems", reply=outcome.summary())
            events.add_log("ok" if outcome.success else "error", outcome.summary()[:300])
            self._speak(outcome.summary())
        except Exception as e:  # noqa: BLE001 - never kill the UI on a task failure
            events.update(state="error", step="Error", reply=str(e))
            events.add_log("error", str(e))
        finally:
            self.busy.release()
            threading.Timer(3.0, self._to_idle).start()

    @staticmethod
    def _to_idle() -> None:
        if events.snapshot()["state"] in {"success", "error"}:
            events.update(state="idle", step="", progress=0.0)

    # --- voice ---
    def _speak(self, text: str) -> None:
        if not self.voice_on or not getattr(self, "_speaker", None):
            return
        events.update(state="speaking")
        self._speaker.speak(text.replace("✅", "").replace("❌", "")[:400])

    def set_voice(self, on: bool) -> str | None:
        if not on:
            self.voice_on = False
            events.update(mic=False)
            return None
        if self.voice_on:
            return None
        from app.voice.engine import Listener, Speaker, VoiceUnavailable, strip_wake_word

        try:
            self._speaker, listener = Speaker(), Listener()
        except VoiceUnavailable as e:
            return str(e)
        self.voice_on = True
        events.update(mic=True)

        def loop() -> None:
            while self.voice_on:
                if self.busy.locked():
                    continue
                events.update(state="listening") if events.snapshot()["state"] == "idle" else None
                try:
                    heard = listener.listen_once()
                except VoiceUnavailable as e:
                    events.add_log("error", str(e))
                    self.voice_on = False
                    events.update(mic=False)
                    return
                command = strip_wake_word(heard) if heard else None
                if command is None:
                    if events.snapshot()["state"] == "listening":
                        events.update(state="idle")
                    continue
                if command.lower() in {"stop", "cancel"}:
                    request_stop(); self._speaker.stop(); continue
                if command:
                    self.submit(command)

        self.voice_thread = threading.Thread(target=loop, daemon=True, name="leo-voice")
        self.voice_thread.start()
        return None


def make_handler(rt: Runtime, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the console quiet
            pass

        def _json(self, payload, status=200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self) -> bool:
            if self.headers.get("Host", "") not in allowed_hosts:
                return False
            origin = self.headers.get("Origin")
            return origin is None or origin.replace("http://", "") in allowed_hosts

        def _api_ok(self) -> bool:
            if not self._host_ok() or not secrets.compare_digest(self.headers.get("X-LEO-Token", ""), rt.token):
                self._json({"error": "forbidden"}, 403)
                return False
            return True

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 1_000_000:
                return {}
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return {}

        def do_GET(self):
            if not self._host_ok():
                return self._json({"error": "forbidden"}, 403)
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                if not self._api_ok():
                    return
                if path == "/api/state":
                    return self._json(events.snapshot())
                if path == "/api/memory":
                    return self._json({"preferences": long_term_memory.all_preferences(), "recent_tasks": long_term_memory.recent_tasks(10)})
                if path == "/api/profile":
                    return self._json(asdict(profile_store.load()))
                return self._json({"error": "not found"}, 404)
            rel = "index.html" if path in {"/", ""} else path.lstrip("/")
            target = (UI_DIR / rel).resolve()
            if UI_DIR.resolve() not in target.parents or not target.is_file():
                return self._json({"error": "not found"}, 404)
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            path = urlparse(self.path).path
            if not path.startswith("/api/") or not self._api_ok():
                return
            data = self._body()
            if path == "/api/command":
                text = str(data.get("text", "")).strip()
                if not text:
                    return self._json({"error": "empty"}, 400)
                if text.lower() in {"stop", "leo stop"}:
                    request_stop()
                    return self._json({"ok": True})
                accepted = rt.submit(text)
                return self._json({"ok": accepted, "error": None if accepted else "LEO is busy with another task."})
            if path == "/api/stop":
                request_stop()
                events.add_log("error", "Emergency stop requested")
                return self._json({"ok": True})
            if path == "/api/confirm":
                rt.answer_confirmation(bool(data.get("approve")))
                return self._json({"ok": True})
            if path == "/api/mode":
                mode = data.get("mode")
                if mode not in {"manual", "assisted", "autonomous"}:
                    return self._json({"error": "bad mode"}, 400)
                rt.leo.task_manager.permissions.set_mode(mode)
                events.update(mode=mode)
                events.add_log("plan", f"Mode set to {mode}")
                return self._json({"ok": True})
            if path == "/api/screen":
                want = data.get("mode")
                if want == "watching":
                    if not settings.screen_capture_enabled:
                        return self._json({"error": "Set SCREEN_CAPTURE_ENABLED=true in .env first."}, 400)
                    rt.monitor.start()
                else:
                    rt.monitor.stop()
                return self._json({"ok": True})
            if path == "/api/voice":
                err = rt.set_voice(bool(data.get("on")))
                return self._json({"ok": err is None, "error": err}, 200 if err is None else 400)
            if path == "/api/profile":
                try:
                    profile_store.save(UserProfile(**data))
                except TypeError as e:
                    return self._json({"error": str(e)}, 400)
                return self._json({"ok": True})
            if path == "/api/memory/forget":
                return self._json({"ok": long_term_memory.forget(str(data.get("key", "")))})
            return self._json({"error": "not found"}, 404)

    return Handler


def open_window(url: str) -> None:
    """Prefer an app-style window (no tabs) in Chrome/Edge; fall back to the default browser."""
    candidates = ["chrome", "google-chrome", "msedge", "chromium", "chromium-browser"]
    for name in candidates:
        exe = shutil.which(name)
        if exe:
            subprocess.Popen([exe, f"--app={url}", "--window-size=1180,760"])
            return
    if sys.platform == "win32":
        for exe in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
            if Path(exe).exists():
                subprocess.Popen([exe, f"--app={url}", "--window-size=1180,760"])
                return
    webbrowser.open(url)


def serve(port: int = 8765, open_browser: bool = True) -> None:
    leo = Leo.bootstrap()
    token = secrets.token_urlsafe(24)
    rt = Runtime(leo, token)
    events.update(mode=leo.task_manager.permissions.mode, provider=leo.provider.name,
                  screen="on_demand" if settings.screen_capture_enabled else "off")
    install_hotkey()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(rt, port))
    url = f"http://127.0.0.1:{port}/?t={token}"
    print(f"LEO UI running at {url}\nPress CTRL+C here to quit.")
    if open_browser:
        open_window(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
