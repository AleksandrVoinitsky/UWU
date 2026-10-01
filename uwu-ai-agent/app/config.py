"""Конфигурация сервиса uwu-ai-agent.

Настройки читаются из переменных окружения (см. ``.env.example``) через
``pydantic-settings``. Модель/параметры LLM задаются здесь (не в админке ядра):
ядро управляет только промптами и правами агента.

См. также: :mod:`app.core_client`, :mod:`app.graph`.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Глобальные настройки агента."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Ядро UWU ---
    # Базовый URL ядра (REST API). В docker-compose задаётся как
    # http://app:8000 (имя сервиса внутри сети).
    core_base_url: str = "http://localhost:8000"
    # API-ключ агента (тот же, что передаётся ядру через AGENT_API_KEY).
    # Обязателен для обращения к /api/agent/*.
    agent_api_key: str = ""
    # Временный пароль по умолчанию, который агент сообщает покупателю при
    # регистрации нового аккаунта (совпадает с CUSTOMER_DEFAULT_PASSWORD в ядре).
    customer_default_password: str = "1242"

    # --- LLM (OpenAI-совместимый API; пустой ключ — fallback-режим) ---
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 512
    # Таймаут LLM-вызова (сек).
    llm_timeout: float = 30.0

    # --- Цикл обработки ---
    # Интервал опроса входящих (сек), когда webhook не используется.
    poll_interval: float = 2.0
    # Включить фоновый polling /inbox (webhook при этом тоже работает).
    enable_polling: bool = True
    # Максимум сообщений диалога, передаваемых в контекст LLM.
    max_history: int = 20

    # --- Сервис ---
    app_name: str = "uwu-ai-agent"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек."""
    return Settings()


settings = get_settings()
