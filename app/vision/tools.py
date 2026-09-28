from __future__ import annotations

from app.providers.base import Message, ProviderError
from app.providers.factory import get_provider
from app.security.permissions import PermissionLevel
from app.tools.base import Tool, ToolResult
from app.vision.screen import ScreenUnavailable, active_window_title, capture_screenshot, ocr_text


class ScreenLookTool(Tool):
    name = "screen.look"
    description = (
        "Look at the user's current screen and answer a question about it "
        "(what's visible, read an error, find a button, etc.). Use whenever the user "
        "refers to 'this', 'my screen', 'the error', or you need to see before acting."
    )
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {
        "type": "object",
        "properties": {"question": {"type": "string", "description": "What to look for / answer"}},
        "required": ["question"],
    }

    def run(self, question: str = "Describe what is on the screen.", **kwargs) -> ToolResult:
        try:
            path = capture_screenshot()
        except ScreenUnavailable as e:
            return ToolResult(success=False, error=str(e))
        text = ocr_text(path)
        title = active_window_title()
        prompt = (
            f"Active window: {title or 'unknown'}\n"
            f"OCR text (may be empty): {text[:3000]}\n\n"
            f"User question about the screen: {question}\n"
            "Answer concisely, based only on what is visible."
        )
        try:
            result = get_provider().vision([Message(role="user", content=prompt)], [path])
        except ProviderError as e:
            return ToolResult(success=False, error=f"Vision model unavailable: {e}", data={"ocr_text": text})
        return ToolResult(
            success=True,
            data={"answer": result.text, "active_window": title, "screenshot": path},
            verification="Captured the screen and analysed it with the vision model.",
        )


class ScreenReadTextTool(Tool):
    name = "screen.read_text"
    description = "OCR the current screen locally (no image leaves the computer) and return the text."
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, **kwargs) -> ToolResult:
        try:
            path = capture_screenshot()
        except ScreenUnavailable as e:
            return ToolResult(success=False, error=str(e))
        text = ocr_text(path)
        if not text:
            return ToolResult(success=False, error="No text found, or OCR is not installed (pip install pytesseract + Tesseract).")
        return ToolResult(success=True, data={"text": text, "active_window": active_window_title()})
