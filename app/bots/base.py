"""Базовые абстракции интеграции с ботами мессенджеров.

Каждый адаптер (Telegram, MAX) реализует единый интерфейс :class:`BotAdapter`:
приём входящих сообщений через колбэк :attr:`on_message` и отправку ответов.
Это позволяет сервису не зависеть от конкретного мессенджера.

См. также: :mod:`app.bots.telegram`, :mod:`app.bots.max`,
:mod:`app.bots.service`.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

# Каналы мессенджеров (совпадают с Chat.channel).
CHANNEL_TELEGRAM = "telegram"
CHANNEL_MAKS = "maks"


def strip_markdown(text: str) -> str:
    """Преобразует простую Markdown-разметку в обычный текст.

    Ответы AI-агента могут содержать ``**жирный**``, ``*курсив*``, списки и ссылки,
    которые мессенджеры (Telegram/MAX) не отображают без ``parse_mode``. Эта функция
    убирает распространённую разметку, оставляя читаемый текст.

    См. также: :func:`app.bots.service.deliver_outgoing`.
    """
    if not text:
        return text
    # Ссылки [text](url) → text; картинки ![alt](url) → alt.
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    # Жирный **text** / __text__.
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    # Курсив *text* / _text_.
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", text)
    # Инлайн-код `text` и зачёркивание ~~text~~.
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    # Заголовки (# ## ### …) и маркеры списков (- * +, 1. 2.).
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}[-*+]\s+", "• ", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}\d+[.)]\s+", "", text, flags=re.MULTILINE)
    # Горизонтальные линии (--- / ***).
    text = re.sub(r"^\s{0,3}([-*_])\s*\1\s*\1[ \t]*$", "", text, flags=re.MULTILINE)
    return text.strip()


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
