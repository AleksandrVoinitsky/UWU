"""Базовые классы ORM-моделей.

См. также: :mod:`app.core.database`, :mod:`app.models.enums`.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TimestampMixin:
    """Добавляет ``created_at`` / ``updated_at``."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class IdMixin:
    """Целочисленный первичный ключ."""

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
