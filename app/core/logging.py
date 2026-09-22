"""Настройка логирования приложения.

Единая точка инициализации логгера. Записи пишутся в ``stdout`` (в Docker это
собирается через ``docker logs``); уровень задаётся настройкой ``LOG_LEVEL``.

Идемпотентность: :func:`setup_logging` выполняется один раз за процесс, а
:func:`get_logger` безопасно вызывать из любого модуля — он гарантирует, что
корневой логгер уже настроен.

См. также: :mod:`app.core.config`, :mod:`app.main`.
"""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False

_LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def setup_logging(level: int | str = logging.INFO) -> None:
    """Настраивает корневой логгер один раз за процесс.

    :param level: уровень логирования (число или имя, напр. ``"INFO"``).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    # Заменяем существующие обработчики — защита от дублей при перезагрузке.
    for existing in root.handlers[:]:
        root.removeHandler(existing)
        existing.close()
    root.addHandler(handler)

    # Access-логи uvicorn не дублируем в корневой логгер (они шумные).
    logging.getLogger("uvicorn.access").propagate = False

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Возвращает логгер модуля, гарантируя инициализацию логирования."""
    setup_logging()
    return logging.getLogger(name)
