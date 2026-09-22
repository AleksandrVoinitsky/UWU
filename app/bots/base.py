"""Базовые абстракции интеграции с ботами мессенджеров.

Каждый адаптер (Telegram, MAX) реализует единый интерфейс :class:`BotAdapter`:
приём входящих сообщений через колбэк :attr:`on_message` и отправку ответов.
Это позволяет сервису не зависеть от конкретного мессенджера.

См. также: :mod:`app.bots.telegram`, :mod:`app.bots.max`,
:mod:`app.bots.service`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

# Каналы мессенджеров (совпадают с Chat.channel).
CHANNEL_TELEGRAM = "telegram"
CHANNEL_MAKS = "maks"


@dataclass(frozen=True)
class IncomingMessage:
    """Нормализованное входящее сообщение из мессенджера."""

    channel: str
    external_chat_id: str  # внешний id чата/пользователя
    sender_name: str
    text: str


# Колбэк, вызываемый адаптером при получении входящего сообщения.
MessageCallback = Callable[[IncomingMessage], Awaitable[None]]


class BotAdapter(ABC):
    """Интерфейс адаптера конкретного мессенджера."""

    #: Канал ("telegram" | "maks").
    channel: str

    def __init__(self, on_message: MessageCallback) -> None:
        self.on_message = on_message

    @abstractmethod
    async def run(self) -> None:
        """Запускает цикл приёма сообщений (long polling). Блокирует до stop()."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Останавливает приём сообщений."""

    @abstractmethod
    async def send_message(self, external_chat_id: str, text: str) -> None:
        """Отправляет сообщение пользователю/чату в мессенджере."""
