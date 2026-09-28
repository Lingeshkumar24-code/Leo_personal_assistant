from PIL import Image

from app.core import stop
from app.providers.base import GenerationResult
from app.vision import screen, tools as vtools
from app.voice.engine import strip_wake_word


def test_wake_word_parsing():
    assert strip_wake_word("leo open chrome") == "open chrome"
    assert strip_wake_word("Leo, what's on my screen?") == "what's on my screen?"
    assert strip_wake_word("leo") == ""
    assert strip_wake_word("hello there friend") is None


def test_stop_flag():
    stop.clear_stop()
    assert not stop.stop_requested()
    stop.request_stop()
    assert stop.stop_requested()
    stop.clear_stop()


def test_screen_look_reports_disabled_when_off(monkeypatch):
    monkeypatch.setattr(screen.settings.__class__, "screen_capture_enabled", False, raising=False)
    monkeypatch.setattr(vtools, "capture_screenshot", lambda: (_ for _ in ()).throw(screen.ScreenUnavailable("off")))
    result = vtools.ScreenLookTool().run(question="what is this?")
    assert not result.success and "off" in result.error


def test_screen_look_uses_vision_model(monkeypatch, tmp_path):
    img = tmp_path / "s.png"
    Image.new("RGB", (100, 60), "white").save(img)

    class FakeProvider:
        def vision(self, messages, image_paths):
            assert image_paths == [str(img)]
            return GenerationResult(text="A white window.")

    monkeypatch.setattr(vtools, "capture_screenshot", lambda: str(img))
    monkeypatch.setattr(vtools, "get_provider", lambda: FakeProvider())
    result = vtools.ScreenLookTool().run(question="describe")
    assert result.success and result.data["answer"] == "A white window."
