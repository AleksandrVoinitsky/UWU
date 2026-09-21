"""Схемы аутентификации и пользователей.

См. также: :mod:`app.models.users`, :mod:`app.api.auth`.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    """Запрос на вход."""

    login: str
    password: str


class TokenResponse(BaseModel):
    """Ответ с токеном доступа."""

    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    """Публичное представление пользователя."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    email: str | None  # str (не EmailStr) — выход не должен падать на «невалидных» адресах
    full_name: str | None
    is_active: bool
    is_admin: bool
    language: str
    role_id: int | None
    last_login_at: datetime | None


class UserCreate(BaseModel):
    """Создание пользователя (администратор)."""

    login: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=4, max_length=128)
    email: EmailStr | None = None
    full_name: str | None = None
    is_active: bool = True
    is_admin: bool = False
    language: str = "ru"
    role_id: int | None = None


class UserUpdate(BaseModel):
    """Обновление пользователя."""

    password: str | None = Field(default=None, min_length=4, max_length=128)
    email: EmailStr | None = None
    full_name: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None
    language: str | None = None
    role_id: int | None = None


class RoleOut(BaseModel):
    """Представление роли."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    permissions: list[str]


class RoleCreate(BaseModel):
    """Создание/обновление роли."""

    key: str = Field(min_length=2, max_length=50)
    name: str
    permissions: list[str] = Field(default_factory=list)


class PermissionOut(BaseModel):
    """Право (ключ + описание)."""

    key: str
    description: str
