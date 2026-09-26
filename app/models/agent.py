"""Модели управления AI-агентом (консультант покупателей).

Хранят управляемую из админки конфигурацию агента: глобальные настройки,
версионируемые промпты, реестр инструментов (действий), API-ключи, а также
журнал запусков (``AgentRun``) и очередь одобрений (``AgentApproval``) для
human-in-the-loop.

Сам агент выполняется в отдельном репозитории/контейнере и обращается к ядру
через REST API; эти таблицы — «плоскость управления» (control plane) агента.

См. также: :mod:`app.services.agent_service`, :mod:`app.web.agent_admin`,
:mod:`app.models.base`.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin

# Политики одобрения инструмента (human-in-the-loop по порогу).
APPROVAL_POLICIES = ("auto", "threshold", "always")

# Статусы запуска агента.
RUN_STATUSES = ("ok", "error", "approval_pending", "rejected")

# Статусы одобрения.
APPROVAL_STATUSES = ("pending", "approved", "rejected")

# Права агента (минимальный набор, расширяется по необходимости).
AGENT_PERMISSIONS = (
    "catalog.read",
    "documents.read",
    "documents.write",
    "reports.read",
)

# Значения глобальных настроек агента по умолчанию (ключ -> значение-строка).
DEFAULT_AGENT_CONFIG: dict[str, str] = {
    "model": "",                       # имя модели (пусто = провайдер по умолчанию)
    "temperature": "0.3",
    "max_history": "20",               # последних сообщений диалога
    "default_responder": "agent",      # agent | operator
    "approval_threshold_amount": "5000",  # порог суммы для политики threshold (₽)
    "fallback_message": "Извините, я сейчас не могу ответить. Оператор свяжется с вами.",
    "max_tokens": "1024",
}


class AgentConfig(Base, IdMixin, TimestampMixin):
    """Одна глобальная настройка агента (ключ -> значение)."""

    __tablename__ = "agent_configs"

    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class AgentPrompt(Base, IdMixin, TimestampMixin):
    """Промпт (системный или узла графа) с версиями."""

    __tablename__ = "agent_prompts"

    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Номер активной версии (указывает на AgentPromptVersion.version).
    active_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    versions: Mapped[list["AgentPromptVersion"]] = relationship(
        back_populates="prompt",
        cascade="all, delete-orphan",
        order_by="AgentPromptVersion.version",
    )


class AgentPromptVersion(Base, IdMixin):
    """Конкретная версия промпта (история не удаляется)."""

    __tablename__ = "agent_prompt_versions"

    prompt_id: Mapped[int] = mapped_column(ForeignKey("agent_prompts.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    # Разрешённые переменные-плейсхолдеры (например {customer}, {context}).
    variables: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    prompt: Mapped[AgentPrompt] = relationship(back_populates="versions")


class AgentTool(Base, IdMixin, TimestampMixin):
    """Инструмент (действие) агента — тонкая обёртка над REST-эндпоинтом ядра."""

    __tablename__ = "agent_tools"

    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)  # для LLM
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    method: Mapped[str] = mapped_column(String(10), default="GET", nullable=False)
    params_schema: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    permission: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # auto | threshold | always (см. APPROVAL_POLICIES).
    approval_policy: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)
    approval_threshold_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rate_limit: Mapped[int] = mapped_column(Integer, default=60, nullable=False)


class AgentApiKey(Base, IdMixin, TimestampMixin):
    """API-ключ агента (сам ключ не хранится — только SHA-256 хеш)."""

    __tablename__ = "agent_api_keys"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentRun(Base, IdMixin):
    """Журнал одного запуска агента (аудит и трассировка)."""

    __tablename__ = "agent_runs"

    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chat_id: Mapped[int | None] = mapped_column(ForeignKey("chats.id"), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_versions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    tool_calls: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="ok", nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentApproval(Base, IdMixin, TimestampMixin):
    """Запрос одобрения действия агента (human-in-the-loop)."""

    __tablename__ = "agent_approvals"

    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    chat_id: Mapped[int | None] = mapped_column(ForeignKey("chats.id"), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    tool_key: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resume_value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
