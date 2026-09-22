"""Адаптер мессенджера MAX (VK) через библиотеку maxapi.

Поддерживает прямые сообщения пользователя боту (основной сценарий «клиент
пишет боту»): входящее сообщение маппится по ``sender.user_id``, ответ
отправляется туда же через ``send_message(user_id=...)``.

См. также: :mod:`app.bots.base`, :mod:`app.bots.service`.
"""
from __future__ import annotations

from maxapi import Bot as MaxBot
from maxapi import Dispatcher as MaxDispatcher

from app.bots.base import CHANNEL_MAKS, BotAdapter, IncomingMessage
from app.core.logging import get_logger

logger = get_logger("app.bots.max")


class MaxAdapter(BotAdapter):
    """Приём/отправка сообщений через MAX Bot API (long polling)."""

    channel = CHANNEL_MAKS

    def __init__(self, token: str, on_message) -> None:
        super().__init__(on_message)
        self._bot = MaxBot(token=token)
        self._dp = MaxDispatcher()

        @self._dp.message_created
        async def _handle(event) -> None:
            msg = event.message
            sender = msg.sender
            if sender is not None:
                external_id = str(sender.user_id)
                name = sender.full_name() or "Неизвестно"
            else:
                external_id = str(msg.recipient.chat_id or "")
                name = "Неизвестно"
            await self.on_message(
                IncomingMessage(
                    channel=self.channel,
                    external_chat_id=external_id,
                    sender_name=name,
                    text=msg.text or "",
                )
            )

    async def run(self) -> None:
        logger.info("MAX bot polling started")
        await self._dp.start_polling(self._bot)

    async def shutdown(self) -> None:
        await self._dp.stop_polling()

    async def send_message(self, external_chat_id: str, text: str) -> None:
        await self._bot.send_message(user_id=int(external_chat_id), text=text)
