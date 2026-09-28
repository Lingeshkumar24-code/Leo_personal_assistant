from app.tools.registry import build_default_registry


def test_all_capabilities_registered_and_implemented():
    registry = build_default_registry()
    names = {t.name for t in registry.implemented()}
    for name in ["filesystem.find", "filesystem.delete", "memory.remember", "computer.open_application",
                 "browser.open", "documents.edit_docx", "coding.run_tests", "screen.look",
                 "jobs.search", "jobs.prepare_application", "jobs.submit_application", "system.set_volume"]:
        assert name in names
    assert registry.planned() == []


def test_high_risk_tools_are_marked():
    registry = build_default_registry()
    for name in ["filesystem.delete", "jobs.submit_application"]:
        assert registry.get(name).permission_level.name == "HIGH_RISK"


def test_tool_specs_have_required_fields():
    for spec in build_default_registry().as_tool_specs():
        assert spec.name and spec.description and isinstance(spec.parameters, dict)
