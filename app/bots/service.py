"""Оркестрация ботов: реестр адаптеров, маршрутизация сообщений, настройки.

Входящие сообщения из мессенджеров сохраняются в ``Chat``/``Message`` и
появляются в интерфейсе оператора; ответ оператора уходит обратно через
соответствующий адаптер.

См. также: :mod:`app.bots.base`, :mod:`app.bots.telegram`,
:mod:`app.bots.max`, :mod:`app.models.messaging`, :mod:`app.models.bot`.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bots.base import (
    CHANNEL_MAKS,
    CHANNEL_TELEGRAM,
    BotAdapter,
    IncomingMessage,
    MessageCallback,
)
from app.core.logging import get_logger
from app.models.bot import BotConfig
from app.models.messaging import Chat, Message

logger = get_logger("app.bots")

# Известные каналы (для формы настроек в админке).
BOT_CHANNELS: dict[str, str] = {
    CHANNEL_TELEGRAM: "Telegram",
    CHANNEL_MAKS: "MAX",
}


class BotManager:
    """Реестр запущенных адаптеров ботов (по каналу)."""

    def __init__(self) -> None:
        self._adapters: dict[str, BotAdapter] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def register(self, adapter: BotAdapter) -> None:
        self._adapters[adapter.channel] = adapter

    def get(self, channel: str) -> BotAdapter | None:
        return self._adapters.get(channel)

    def start(self, adapter: BotAdapter) -> None:
        """Регистрирует адаптер и запускает его polling фоновой задачей."""
        self.register(adapter)
        old_task = self._tasks.get(adapter.channel)
        if old_task is not None and not old_task.done():
            old_task.cancel()
        self._tasks[adapter.channel] = asyncio.create_task(adapter.run())

    async def stop_all(self) -> None:
        for adapter in self._adapters.values():
            try:
                await adapter.shutdown()
            except Exception:  # noqa: BLE001
                logger.exception("Error stopping bot %s", adapter.channel)
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._adapters.clear()
        self._tasks.clear()

    def clear(self) -> None:
        """Сбрасывает реестр (для тестов)."""
        self._adapters.clear()
        self._tasks.clear()


# Синглтон реестра (используется веб-слоем для отправки ответов).
bot_manager = BotManager()


def create_adapter(channel: str, token: str, on_message: MessageCallback) -> BotAdapter:
    """Фабрика адаптера по каналу."""
    if channel == CHANNEL_TELEGRAM:
        from app.bots.telegram import TelegramAdapter

        return TelegramAdapter(token, on_message)
    if channel == CHANNEL_MAKS:
        from app.bots.max import MaxAdapter

        return MaxAdapter(token, on_message)
    raise ValueError(f"Unknown bot channel: {channel}")


# --- Настройки ботов ---


async def get_configs(session: AsyncSession) -> list[BotConfig]:
    result = await session.execute(select(BotConfig).order_by(BotConfig.channel))
    return list(result.scalars())


async def get_config(session: AsyncSession, channel: str) -> BotConfig | None:
    return (
        await session.execute(
            select(BotConfig).where(BotConfig.channel == channel)
        )
    ).scalar_one_or_none()


async def upsert_config(
    session: AsyncSession,
    channel: str,
    *,
    enabled: bool,
    token: str | None,
    name: str | None,
) -> BotConfig:
    """Создаёт или обновляет конфигурацию бота.

    Пустой ``token`` не перезаписывает уже сохранённый (поле маскируется в UI).
    """
    cfg = await get_config(session, channel)
    if cfg is None:
        cfg = BotConfig(channel=channel)
        session.add(cfg)
    cfg.enabled = enabled
    if token:
        cfg.token = token
    cfg.name = name or None
    await session.commit()
    await session.refresh(cfg)
    return cfg


# --- Приём/отправка сообщений ---


async def find_or_create_chat(
    session: AsyncSession, channel: str, external_id: str, name: str
) -> Chat:
    """Находит чат по каналу и внешнему id или создаёт новый."""
    stmt = select(Chat).where(
        Chat.channel == channel, Chat.external_id == external_id
    )
    chat = (await session.execute(stmt)).scalar_one_or_none()
    if chat is None:
        chat = Chat(name=name or "Чат", channel=channel, external_id=external_id)
        session.add(chat)
        await session.flush()
    return chat


async def store_incoming(
    session_factory: async_sessionmaker, message: IncomingMessage
) -> None:
    """Сохраняет входящее сообщение в БД (вызывается адаптером)."""
    async with session_factory() as session:
        chat = await find_or_create_chat(
            session, message.channel, message.external_chat_id, message.sender_name
        )
        session.add(Message(chat_id=chat.id, direction="in", text=message.text))
        chat.last_message_at = datetime.now(timezone.utc)
        await session.commit()
    logger.info(
        "Incoming %s from %s (%s)",
        message.channel,
        message.sender_name,
        message.external_chat_id,
    )


async def deliver_outgoing(chat: Chat, text: str) -> None:
    """Отправляет ответ оператора в мессенджер через активный адаптер."""
    adapter = bot_manager.get(chat.channel)
    if adapter is None or not chat.external_id:
        logger.warning(
            "Нет активного адаптера для канала %s (external_id=%s)",
            chat.channel,
            chat.external_id,
        )
        return
    try:
        await adapter.send_message(chat.external_id, text)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Не удалось отправить сообщение в %s (%s)",
            chat.channel,
            chat.external_id,
        )


# --- Управление жизненным циклом ---


async def start_bots(session_factory: async_sessionmaker) -> None:
    """Запускает ботов для всех включённых конфигураций с токеном."""
    async with session_factory() as session:
        configs = await get_configs(session)
    for cfg in configs:
        if not cfg.enabled or not cfg.token:
            continue
        try:
            from functools import partial

            adapter = create_adapter(
                cfg.channel, cfg.token, partial(store_incoming, session_factory)
            )
            bot_manager.start(adapter)
            logger.info("Bot %s started", cfg.channel)
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось запустить бота %s", cfg.channel)


async def stop_bots() -> None:
    """Останавливает всех запущенных ботов."""
    await bot_manager.stop_all()
