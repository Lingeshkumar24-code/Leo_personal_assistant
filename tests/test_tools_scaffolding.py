"""Any future not-yet-built tool must fail honestly, never fake success."""
from app.tools.base import NotImplementedTool


def test_not_implemented_tool_fails_honestly():
    class Future(NotImplementedTool):
        name = "future.thing"

    result = Future().run()
    assert Future.status == "planned" and result.success is False
    assert "not implemented" in result.error.lower()
