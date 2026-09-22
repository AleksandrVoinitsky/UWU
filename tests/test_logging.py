"""Тесты логирования и обработки ошибок.

См. также: :mod:`app.core.logging`, :mod:`app.main`.
"""
from __future__ import annotations

import logging


def test_setup_logging_is_idempotent():
    """Повторный вызов setup_logging не плодит дублирующие обработчики."""
    from app.core.logging import setup_logging

    root = logging.getLogger()
    setup_logging()
    handlers_before = len([h for h in root.handlers if not h.name])
    setup_logging()
    handlers_after = len([h for h in root.handlers if not h.name])
    assert handlers_before == handlers_after
    assert handlers_before >= 1


def test_get_logger_returns_configured_logger():
    from app.core.logging import get_logger

    logger = get_logger("app.test")
    assert logger.name == "app.test"
    # Логгер должен распространять записи в корневой (настроенный) логгер.
    assert logger.propagate is True


async def test_request_logging_middleware(client, seeded_session, caplog):
    """Каждый не-статичный запрос логируется с методом, путём и статусом."""
    caplog.set_level(logging.INFO)
    resp = await client.get("/login")
    assert resp.status_code == 200
    messages = [r.getMessage() for r in caplog.records]
    assert any("GET /login -> 200" in m for m in messages), messages


def test_unhandled_exception_handler_registered():
    """На приложении зарегистрирован единый обработчик необработанных ошибок."""
    from app.main import app

    assert Exception in app.exception_handlers
