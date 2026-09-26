"""Настройки интеграции с ботами мессенджеров (Telegram, MAX).

Хранит по одной конфигурации на канал: токен, флаг активности и отображаемое имя.
Токен — секрет, хранится в БД и маскируется в интерфейсе администратора.

См. также: :mod:`app.bots`, :mod:`app.models.base`.
"""
from __future__ import annotations

from sqlalchemy import Boolean, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin


class BotConfig(Base, IdMixin, TimestampMixin):
    """Конфигурация одного бота (одна запись на канал)."""

    __tablename__ = "bot_configs"

    # Канал: "telegram" | "maks".
    channel: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    # Токен бота (секрет).
    token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
