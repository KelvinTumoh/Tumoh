"""Tests for deployment hardening and production-readiness checks."""


from ide_core.config.settings import IDESettings
from ide_core.deployment import ProductionReadiness


def test_short_jwt_secret_warns():
    settings = IDESettings(jwt_secret="short")
    warnings = ProductionReadiness(settings).check()
    assert any("shorter than 32 bytes" in w for w in warnings)


def test_placeholder_jwt_secret_warns():
    settings = IDESettings(jwt_secret="change-me-in-production")
    warnings = ProductionReadiness(settings).check()
    assert any("placeholder" in w for w in warnings)


def test_none_jwt_algorithm_warns():
    settings = IDESettings(jwt_algorithm="none")
    warnings = ProductionReadiness(settings).check()
    assert any("'none' is insecure" in w for w in warnings)


def test_disabled_security_manager_warns():
    settings = IDESettings(enable_security_manager=False)
    warnings = ProductionReadiness(settings).check()
    assert any("Security manager is disabled" in w for w in warnings)


def test_strong_settings_pass():
    settings = IDESettings(
        jwt_secret="a-very-strong-production-secret-that-is-at-least-32-bytes",
        jwt_algorithm="HS256",
        enable_security_manager=True,
        enable_multi_tenant=True,
        ide_host="127.0.0.1",
    )
    warnings = ProductionReadiness(settings).check()
    assert warnings == []
