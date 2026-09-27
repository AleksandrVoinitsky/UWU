"""Адаптер Telegram (aiogram 3.x).

См. также: :mod:`app.bots.base`, :mod:`app.bots.service`.
"""
from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import Message as TelegramMessage

from app.bots.base import CHANNEL_TELEGRAM, BotAdapter, IncomingMessage
from app.core.logging import get_logger

logger = get_logger("app.bots.telegram")

# Пауза перед перезапуском long polling после неожиданной остановки (сбой сети).
_RETRY_DELAY = 5.0


class TelegramAdapter(BotAdapter):
    """Приём/отправка сообщений через Telegram Bot API (long polling)."""

    channel = CHANNEL_TELEGRAM

    def __init__(self, token: str, on_message) -> None:
        super().__init__(on_message)
        self._token = token
        self._bot = Bot(token=token)
        self._dp = Dispatcher()
        self._stopped = False

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
        # Переживаем кратковременные сбои сети: если long polling неожиданно
        # останавливается (например, api.telegram.org был недоступен при старте),
        # перезапускаем его, а не оставляем бота «мёртвым» до ручного рестарта.
        while not self._stopped:
            try:
                # uvicorn сам управляет сигналами; сессию не закрываем — она
                # переиспользуется при перезапуске цикла.
                await self._dp.start_polling(
                    self._bot,
                    handle_signals=False,
                    close_bot_session=False,
                )
            except Exception as exc:  # noqa: BLE001 — сетевые сбои не фатальны
                logger.warning("Telegram polling error: %s", exc)
            if self._stopped:
                break
            logger.warning(
                "Telegram polling stopped unexpectedly — restart in %.0fs",
                _RETRY_DELAY,
            )
            await asyncio.sleep(_RETRY_DELAY)
        if self._bot.session:
            await self._bot.session.close()
        logger.info("Telegram bot stopped")

    async def shutdown(self) -> None:
        self._stopped = True
        await self._dp.stop_polling()

    async def send_message(self, external_chat_id: str, text: str) -> None:
        await self._bot.send_message(chat_id=int(external_chat_id), text=text)
