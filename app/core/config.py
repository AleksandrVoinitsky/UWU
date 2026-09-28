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
    database_url: str = "postgresql+asyncpg://uwu:uwu@localhost:5432/uwu?ssl=disable"

    # --- Администратор (создаётся при первом запуске) ---
    admin_login: str = "admin"
    admin_password: str = "admin"
    admin_email: str = "admin@example.com"

    # --- Безопасность ---
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 480
    jwt_algorithm: str = "HS256"

    # --- Домен / валюта ---
    default_currency: str = "RUB"
    default_language: str = "ru"

    # --- Сервис ---
    app_name: str = "UWU"
    uploads_dir: str = "./uploads"  # каталог для загружаемых изображений
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR | CRITICAL
    # Окружение развёртывания: "development" | "production". В production
    # небезопасные настройки безопасности (слабый SECRET_KEY/пароль) блокируют
    # запуск приложения.
    environment: str = "development"
    # Режим разработки MiniApp: пропускает проверку подписи initData (для
    # локального тестирования). В проде должен быть выключен.
    miniapp_dev: bool = False

    # --- Семантический поиск (pgvector + эмбеддинги) ---
    # OpenAI-совместимый эндпоинт эмбеддингов (пустая строка — семантический
    # поиск выключен, работает fallback по ключевым словам).
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    # Размерность вектора эмбеддингов (должна совпадать с колонкой pgvector;
    # при смене модели — новая миграция).
    embedding_dim: int = 1536

    # --- AI-агент (отдельный сервис uwu-ai-agent) ---
    # URL webhook-эндпоинта агента (POST /webhook). Пустая строка — ядро не
    # уведомляет агента о новых входящих сообщениях.
    agent_webhook_url: str = ""
    # Таймаут (сек) запроса-уведомления агенту (best-effort, не блокирует чат).
    agent_webhook_timeout: float = 3.0
    # API-ключ агента: если задан, ядро при старте гарантирует существование
    # записи ключа с таким значением (идемпотентно). Тот же ключ передаётся
    # сервису uwu-ai-agent через его переменную окружения — так развёртывание
    # агента работает «из коробки» без ручного создания ключа в админке.
    agent_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек."""
    return Settings()


settings = get_settings()
