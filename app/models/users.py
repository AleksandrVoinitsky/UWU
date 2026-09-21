"""Пользователи, роли и права доступа.

Администратор (:attr:`User.is_admin`) не видит торговый интерфейс, но управляет
учётными записями и правами. Права описаны набором строковых ключей (см.
:data:`PERMISSIONS`), хранящихся в JSON-колонке :attr:`Role.permissions`.

См. также: :mod:`app.core.security`, :mod:`app.services.user_service`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin
from app.models.enums import RoleKey

# Набор доступных прав (ключ -> назначение).
PERMISSIONS: dict[str, str] = {
    "users.manage": "Управление пользователями и правами",
    "catalog.read": "Просмотр справочников",
    "catalog.write": "Редактирование справочников",
    "documents.read": "Просмотр документов",
    "documents.write": "Создание/редактирование документов",
    "documents.post": "Проведение документов",
    "reports.read": "Просмотр отчётов",
    "service.settings": "Настройки сервиса (константы)",
}

# Права по умолчанию для встроенных ролей.
DEFAULT_ROLE_PERMISSIONS: dict[RoleKey, list[str]] = {
    RoleKey.ADMIN: list(PERMISSIONS.keys()),
    RoleKey.OPERATOR: [
        "catalog.read",
        "catalog.write",
        "documents.read",
        "documents.write",
        "documents.post",
        "reports.read",
    ],
    RoleKey.ACCOUNTANT: [
        "catalog.read",
        "documents.read",
        "documents.post",
        "reports.read",
    ],
}


class Role(Base, IdMixin, TimestampMixin):
    """Роль с набором прав."""

    __tablename__ = "roles"

    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="role")

    def has_permission(self, key: str) -> bool:
        return key in (self.permissions or [])


class User(Base, IdMixin, TimestampMixin):
    """Учётная запись пользователя."""

    __tablename__ = "users"

    login: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    language: Mapped[str] = mapped_column(String(5), default="ru", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)
    role: Mapped[Role | None] = relationship(back_populates="users")

    def has_permission(self, key: str) -> bool:
        """Администратор имеет все права; иначе — по роли."""
        if self.is_admin:
            return True
        if self.role is None:
            return False
        return self.role.has_permission(key)
