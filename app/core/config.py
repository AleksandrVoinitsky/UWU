"""Конфигурация сервиса.

Настройки читаются из переменных окружения (см. ``.env.example``) с помощью
``pydantic-settings``. Это позволяет задавать параметры развёртывания (строку
подключения к БД, учётную запись администратора, секретный ключ и т.д.) без
изменения кода — ключевое требование для запуска под Docker.

См. также: :mod:`app.core.database`, :mod:`app.core.security`.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Глобальные настройки приложения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- База данных ---
    database_url: str = "postgresql+asyncpg://uwu:uwu@localhost:5432/uwu"

    # --- Администратор (создаётся при первом запуске) ---
    admin_login: str = "admin"
    admin_password: str = "admin"
    admin_email: str = "admin@uwu.local"

    # --- Безопасность ---
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 480
    jwt_algorithm: str = "HS256"

    # --- Домен / валюта ---
    default_currency: str = "RUB"
    default_language: str = "ru"

    # --- Сервис ---
    app_name: str = "UWU"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек."""
    return Settings()


settings = get_settings()
