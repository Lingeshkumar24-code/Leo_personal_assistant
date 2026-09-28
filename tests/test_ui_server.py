import threading
import time
from http.server import ThreadingHTTPServer

import pytest
import requests

from app.core import events
from app.core.config import settings
from app.ui.server import Runtime, make_handler
from tests.fake_leo import make_leo

TOKEN = "test-token"


@pytest.fixture
def server(tmp_path):
    old = settings.data_dir
    object.__setattr__(settings, "data_dir", tmp_path)
    rt = Runtime(make_leo(), TOKEN)
    rt.leo.task_manager.permissions.set_mode("assisted")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(rt, 0))
    port = srv.server_address[1]
    # handler validates Host against the real port
    srv.RequestHandlerClass = make_handler(rt, port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}", tmp_path
    srv.shutdown()
    object.__setattr__(settings, "data_dir", old)


H = {"X-LEO-Token": TOKEN}


def wait_for(cond, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_api_requires_token_and_valid_host(server):
    base, _ = server
    assert requests.get(f"{base}/api/state").status_code == 403
    assert requests.get(f"{base}/api/state", headers={"X-LEO-Token": "wrong"}).status_code == 403
    assert requests.get(f"{base}/api/state", headers={**H, "Host": "evil.example.com"}).status_code == 403   # DNS rebinding
    assert requests.post(f"{base}/api/command", json={"text": "hi"}, headers={**H, "Origin": "http://evil.example.com"}).status_code == 403
    assert requests.get(f"{base}/api/state", headers=H).status_code == 200


def test_ui_files_served_but_no_path_traversal(server):
    base, _ = server
    assert "LEO" in requests.get(f"{base}/").text
    assert requests.get(f"{base}/vendor/three.module.js").status_code == 200
    assert requests.get(f"{base}/../app/core/config.py").status_code == 404
    assert requests.get(f"{base}/%2e%2e/app/core/config.py").status_code == 404


def test_command_runs_real_tool_and_updates_state(server):
    base, _ = server
    r = requests.post(f"{base}/api/command", json={"text": "remember the wifi is fast"}, headers=H).json()
    assert r["ok"]
    assert wait_for(lambda: requests.get(f"{base}/api/state", headers=H).json()["state"] in {"success", "error"})
    state = requests.get(f"{base}/api/state", headers=H).json()
    assert state["state"] == "success" and state["progress"] == 1.0
    assert any("memory.remember" in l["text"] for l in state["log"])


def test_high_risk_action_waits_for_approval_and_can_be_approved(server):
    base, tmp = server
    victim = tmp / "old_notes.txt"
    victim.write_text("bye")
    assert requests.post(f"{base}/api/command", json={"text": f"delete {victim}"}, headers=H).json()["ok"]
    assert wait_for(lambda: requests.get(f"{base}/api/state", headers=H).json()["pending_confirmation"])
    assert victim.exists()                                    # nothing happens before approval
    requests.post(f"{base}/api/confirm", json={"approve": True}, headers=H)
    assert wait_for(lambda: not victim.exists())
    assert list((tmp / "trash").rglob("old_notes.txt"))


def test_denied_action_does_nothing(server):
    base, tmp = server
    victim = tmp / "keep.txt"
    victim.write_text("keep me")
    requests.post(f"{base}/api/command", json={"text": f"delete {victim}"}, headers=H)
    assert wait_for(lambda: requests.get(f"{base}/api/state", headers=H).json()["pending_confirmation"])
    requests.post(f"{base}/api/confirm", json={"approve": False}, headers=H)
    assert wait_for(lambda: requests.get(f"{base}/api/state", headers=H).json()["state"] in {"error", "success"})
    assert victim.exists()


def test_mode_change_and_bad_mode(server):
    base, _ = server
    assert requests.post(f"{base}/api/mode", json={"mode": "autonomous"}, headers=H).status_code == 200
    assert requests.post(f"{base}/api/mode", json={"mode": "root"}, headers=H).status_code == 400
