from app.security.permissions import PermissionManager, PermissionLevel, OperatingMode


def test_manual_mode_requires_confirmation_for_normal():
    pm = PermissionManager(mode=OperatingMode.MANUAL)
    decision = pm.evaluate("computer.open_application", PermissionLevel.NORMAL)
    assert decision.requires_confirmation is True


def test_assisted_mode_auto_runs_normal():
    pm = PermissionManager(mode=OperatingMode.ASSISTED)
    decision = pm.evaluate("computer.open_application", PermissionLevel.NORMAL)
    assert decision.requires_confirmation is False


def test_high_risk_always_requires_confirmation_even_in_autonomous():
    pm = PermissionManager(mode=OperatingMode.AUTONOMOUS)
    decision = pm.evaluate("filesystem.delete", PermissionLevel.HIGH_RISK)
    assert decision.requires_confirmation is True


def test_autonomous_mode_auto_runs_privileged():
    pm = PermissionManager(mode=OperatingMode.AUTONOMOUS)
    decision = pm.evaluate("coding.run_tests", PermissionLevel.PRIVILEGED)
    assert decision.requires_confirmation is False
