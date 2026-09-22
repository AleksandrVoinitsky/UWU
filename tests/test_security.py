"""Тесты проверки настроек безопасности.

См. также: :mod:`app.core.security`, :mod:`app.core.config`.
"""
from __future__ import annotations

import logging


def test_validate_security_settings_clean(monkeypatch):
    """С корректными настройками предупреждений нет."""
    from app.core import security

    monkeypatch.setattr(security.settings, "secret_key", "a" * 40)
    monkeypatch.setattr(security.settings, "admin_password", "StrongPass!123")
    assert security.validate_security_settings() == []


def test_validate_security_settings_detects_defaults(monkeypatch, caplog):
    """Дефолтный SECRET_KEY и слабый пароль админа дают предупреждения."""
    from app.core import security

    monkeypatch.setattr(security.settings, "secret_key", "change-me")
    monkeypatch.setattr(security.settings, "admin_password", "admin")
    caplog.set_level(logging.WARNING)
    warnings = security.validate_security_settings()
    assert len(warnings) >= 1
    assert any("SECRET_KEY" in w for w in warnings)


def test_validate_security_settings_short_key(monkeypatch):
    """Короткий секретный ключ тоже считается небезопасным."""
    from app.core import security

    monkeypatch.setattr(security.settings, "secret_key", "short")
    monkeypatch.setattr(security.settings, "admin_password", "StrongPass!123")
    warnings = security.validate_security_settings()
    assert any("SECRET_KEY" in w for w in warnings)
