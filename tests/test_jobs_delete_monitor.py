import json
import os

import pytest
from PIL import Image

from app.filesystem.tools import DeleteFileTool
from app.jobs import tools as jt
from app.jobs.matching import map_field_to_profile, score_job
from app.jobs.profile import ProfileStore, UserProfile
from app.memory.store import ShortTermMemory
from app.vision import monitor as mon

PROFILE = UserProfile(name="Asha Rao", email="asha@example.com", phone="9999999999",
                      skills=["Python", "LangGraph", "SQL"], preferred_roles=["AI Engineer"])

FORM = """<html><body><form onsubmit="document.title='SUBMITTED';return false;">
<label for=n>Full Name</label><input id=n name=name required>
<label for=e>Email</label><input id=e type=email name=email required>
<label for=p>Phone</label><input id=p type=tel name=phone>
<label for=s>Expected salary</label><input id=s name=salary required>
<label for=r>Resume</label><input id=r type=file>
<button type=submit>Submit</button></form></body></html>"""


def test_score_and_mapping():
    r = score_job("We need Python and SQL experience for this AI Engineer role", PROFILE)
    assert r["score"] == 67 and "LangGraph" in r["unmentioned_skills"] and r["matches_preferred_role"]
    assert map_field_to_profile("Full Name", "name", "text", PROFILE) == "Asha Rao"
    assert map_field_to_profile("Email", "", "email", PROFILE) == "asha@example.com"
    assert map_field_to_profile("Expected salary", "salary", "text", PROFILE) is None  # never guessed


def test_delete_moves_to_trash_and_protects(tmp_path, monkeypatch):
    from app.core.config import settings
    old = settings.data_dir
    object.__setattr__(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings.__class__, "_restore", lambda self: None, raising=False)
    f = tmp_path / "junk.txt"
    f.write_text("x")
    tool = DeleteFileTool()
    result = tool.verify(tool.run(paths=[str(f)]))
    assert result.success and not f.exists()
    assert not tool.run(paths=[str(tmp_path.anchor)]).success          # drive root protected
    assert not tool.run(paths=[str(f)] * 21).success                   # bulk limit
    assert list((tmp_path / "trash").rglob("junk.txt"))                # recoverable, not erased
    object.__setattr__(settings, "data_dir", old)


def test_monitor_skips_unchanged_screens(monkeypatch, tmp_path):
    img = tmp_path / "s.png"
    Image.new("RGB", (50, 50), "blue").save(img)
    monkeypatch.setattr(mon, "capture_screenshot", lambda max_width=1000: str(img))
    monkeypatch.setattr(mon, "ocr_text", lambda p: "hello screen")
    monkeypatch.setattr(mon, "active_window_title", lambda: "Editor")
    stm = ShortTermMemory()
    m = mon.ScreenMonitor(stm)
    assert m.tick() is True and stm.screen_context["visible_text"] == "hello screen"
    assert m.tick() is False


@pytest.fixture
def browser_page(tmp_path, monkeypatch):
    pw = pytest.importorskip("playwright.sync_api")
    p = pw.sync_playwright().start()
    try:
        b = p.chromium.launch()
    except Exception:
        p.stop()
        pytest.skip("Chromium not available")
    page = b.new_page()
    monkeypatch.setattr(jt, "_page", lambda: page)
    yield page
    b.close(); p.stop()


def test_prepare_application_fills_but_never_submits(browser_page, tmp_path, monkeypatch):
    resume = tmp_path / "cv.pdf"; resume.write_bytes(b"%PDF-1.4")
    prof = UserProfile(**{**PROFILE.__dict__, "resume_paths": [str(resume)]})
    monkeypatch.setattr(jt.profile_store, "load", lambda: prof)
    monkeypatch.setattr(jt, "record_application", lambda e: None)
    form = tmp_path / "form.html"; form.write_text(FORM)
    result = jt.PrepareApplicationTool().run(job_url=form.as_uri())
    assert result.success and result.data["submitted"] is False
    assert browser_page.input_value("#n") == "Asha Rao" and browser_page.input_value("#e") == "asha@example.com"
    assert browser_page.input_value("#s") == ""                       # salary left for the user
    assert any("salary" in q["field"].lower() for q in result.data["questions_for_user"])
    assert browser_page.title() != "SUBMITTED"


def test_captcha_page_is_not_bypassed(browser_page, tmp_path):
    page = tmp_path / "c.html"; page.write_text("<html><body><div class='g-recaptcha'></div></body></html>")
    result = jt.PrepareApplicationTool().run(job_url=page.as_uri())
    assert not result.success and "CAPTCHA" in result.error


def test_submit_clicks_only_when_called(browser_page, tmp_path, monkeypatch):
    monkeypatch.setattr(jt, "record_application", lambda e: None)
    form = tmp_path / "form.html"; form.write_text(FORM.replace(" required", ""))
    browser_page.goto(form.as_uri())
    assert jt.SubmitApplicationTool.permission_level.name == "HIGH_RISK"
    assert jt.SubmitApplicationTool().run().success and browser_page.title() == "SUBMITTED"
