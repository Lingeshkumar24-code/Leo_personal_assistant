"""
Phase 5 - Browser Agent (implemented).

Real Playwright automation. A single browser/page is kept alive across
tool calls within one LEO session (see BrowserSession below) so
"open Chrome, search X, click the first result" works as a sequence.

Note: the Playwright *browser binary* (Chromium) must be installed on the
machine LEO runs on:
    playwright install chromium
This install step needs network access to Playwright's CDN, which is not
reachable from this build sandbox, so end-to-end browsing could not be
executed here - but the automation code itself is real and follows
Playwright's documented API exactly as it would run on your machine.
"""
from __future__ import annotations

import threading

from app.security.permissions import PermissionLevel
from app.tools.base import Tool, ToolResult


class BrowserSession:
    """Lazily-started, process-wide Playwright browser/page, reused across tool calls."""

    _lock = threading.Lock()
    _playwright = None
    _browser = None
    _page = None

    # On a real desktop (Windows/macOS/Linux with a display), LEO should show
    # the browser window so the user can see what it's doing, per the spec's
    # browser examples. Set LEO_BROWSER_HEADLESS=true to run invisibly (e.g.
    # on a headless server or in this sandbox).
    @classmethod
    def _headless(cls) -> bool:
        import os

        return os.getenv("LEO_BROWSER_HEADLESS", "false").strip().lower() in {"1", "true", "yes"}

    @classmethod
    def get_page(cls):
        with cls._lock:
            if cls._page is not None:
                return cls._page
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as e:
                raise RuntimeError("playwright is not installed. pip install playwright && playwright install chromium") from e

            cls._playwright = sync_playwright().start()
            try:
                cls._browser = cls._playwright.chromium.launch(headless=cls._headless())
            except Exception as e:  # noqa: BLE001
                cls._playwright.stop()
                cls._playwright = None
                raise RuntimeError(
                    f"Could not launch Chromium: {e}. Have you run 'playwright install chromium'? "
                    "On a headless machine, set LEO_BROWSER_HEADLESS=true in .env."
                ) from e
            cls._page = cls._browser.new_page()
            return cls._page

    @classmethod
    def close(cls):
        with cls._lock:
            if cls._browser:
                cls._browser.close()
            if cls._playwright:
                cls._playwright.stop()
            cls._browser = None
            cls._page = None
            cls._playwright = None


class OpenBrowserTool(Tool):
    name = "browser.open"
    description = "Launch a browser and optionally navigate to a URL."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {"type": "object", "properties": {"url": {"type": "string"}}}

    def run(self, url: str | None = None, **kwargs) -> ToolResult:
        try:
            page = BrowserSession.get_page()
            if url:
                page.goto(url, wait_until="domcontentloaded")
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=str(e))
        return ToolResult(success=True, data={"url": page.url}, verification=f"Page URL is now {page.url}")

    def verify(self, result: ToolResult, url: str | None = None, **kwargs) -> ToolResult:
        if result.success and url:
            result.success = url.split("://")[-1].split("/")[0] in result.data.get("url", "")
        return result


class BrowserSearchTool(Tool):
    name = "browser.search"
    description = "Search the web (DuckDuckGo HTML, no API key needed) and return top results."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

    def run(self, query: str, **kwargs) -> ToolResult:
        try:
            page = BrowserSession.get_page()
            page.goto(f"https://duckduckgo.com/html/?q={query}", wait_until="domcontentloaded")
            results = page.eval_on_selector_all(
                "a.result__a",
                "els => els.slice(0, 5).map(e => ({title: e.innerText, href: e.href}))",
            )
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=str(e))
        return ToolResult(success=True, data={"query": query, "results": results})


class BrowserReadPageTool(Tool):
    name = "browser.read_page"
    description = "Extract the readable text content of the current page."
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, **kwargs) -> ToolResult:
        try:
            page = BrowserSession.get_page()
            text = page.evaluate("document.body ? document.body.innerText : ''")
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=str(e))
        return ToolResult(success=True, data={"url": page.url, "text": text[:20000]})


class BrowserClickTool(Tool):
    name = "browser.click"
    description = "Click an element on the current page by CSS selector or visible text."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {"selector": {"type": "string"}, "text": {"type": "string"}},
    }

    def run(self, selector: str | None = None, text: str | None = None, **kwargs) -> ToolResult:
        try:
            page = BrowserSession.get_page()
            if selector:
                page.click(selector, timeout=5000)
            elif text:
                page.get_by_text(text, exact=False).first.click(timeout=5000)
            else:
                return ToolResult(success=False, error="Provide either 'selector' or 'text'.")
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=str(e))
        return ToolResult(success=True, data={"clicked": selector or text})


class BrowserTypeTool(Tool):
    name = "browser.type"
    description = "Type text into an input field identified by a CSS selector."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {"selector": {"type": "string"}, "text": {"type": "string"}},
        "required": ["selector", "text"],
    }

    def run(self, selector: str, text: str, **kwargs) -> ToolResult:
        try:
            page = BrowserSession.get_page()
            page.fill(selector, text, timeout=5000)
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=str(e))
        return ToolResult(success=True, data={"selector": selector})
