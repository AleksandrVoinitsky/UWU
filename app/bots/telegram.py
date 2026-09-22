"""Адаптер Telegram (aiogram 3.x).

См. также: :mod:`app.bots.base`, :mod:`app.bots.service`.
"""
from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.types import Message as TelegramMessage

from app.bots.base import CHANNEL_TELEGRAM, BotAdapter, IncomingMessage
from app.core.logging import get_logger

logger = get_logger("app.bots.telegram")


class TelegramAdapter(BotAdapter):
    """Приём/отправка сообщений через Telegram Bot API (long polling)."""

    channel = CHANNEL_TELEGRAM

    def __init__(self, token: str, on_message) -> None:
        super().__init__(on_message)
        self._token = token
        self._bot = Bot(token=token)
        self._dp = Dispatcher()

        @self._dp.message()
        async def _handle(message: TelegramMessage) -> None:
            sender = message.from_user
            name = (sender.full_name if sender else None) or "Неизвестно"
            await self.on_message(
                IncomingMessage(
                    channel=self.channel,
                    external_chat_id=str(message.chat.id),
                    sender_name=name,
                    text=message.text or "",
                )
            )

    async def run(self) -> None:
        logger.info("Telegram bot polling started")
        try:
            await self._dp.start_polling(self._bot)
        finally:
            await self._bot.session.close() if self._bot.session else None

    async def shutdown(self) -> None:
        await self._dp.stop_polling()

    async def send_message(self, external_chat_id: str, text: str) -> None:
        await self._bot.send_message(chat_id=int(external_chat_id), text=text)
