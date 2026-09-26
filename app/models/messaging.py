"""Мессенджер: чаты и сообщения (основа для интеграции с ботами).

Чаты привязаны к клиентам (контрагентам) и к каналам (Макс, Telegram и т.д.).
Сама интеграция с ботами пока не реализована — заложена модель и API.

См. также: :mod:`app.models.base`.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin


class Chat(Base, IdMixin, TimestampMixin):
    """Чат с клиентом или ботом."""

    __tablename__ = "chats"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), default="internal", server_default="internal", nullable=False)  # internal | telegram | maks | site
    # Внешний идентификатор чата в мессенджере (chat_id Telegram, user_id MAX) —
    # нужен для отправки ответа оператора обратно в мессенджер.
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    kontragent_id: Mapped[int | None] = mapped_column(ForeignKey("kontragenty.id"), nullable=True)
    # Покупатель интернет-магазина (для чата «сайт»): связывает чат с учётной
    # записью покупателя и используется для отображения в чате продавца.
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat", cascade="all, delete-orphan", order_by="Message.id"
    )
    customer: Mapped["Customer | None"] = relationship()  # noqa: F821


class Message(Base, IdMixin):
    """Сообщение в чате."""

    __tablename__ = "messages"

    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id"), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), default="out", server_default="out", nullable=False)  # in | out
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Прочитано ли получателем. Получатель определяется направлением:
    # "in" (от покупателя) читает оператор; "out" (от оператора) читает покупатель.
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    chat: Mapped[Chat] = relationship(back_populates="messages")
