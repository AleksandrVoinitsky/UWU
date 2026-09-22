"""Интеграция с ботами мессенджеров (Telegram, MAX)."""
from app.bots.base import CHANNEL_MAKS, CHANNEL_TELEGRAM, BotAdapter, IncomingMessage
from app.bots.service import (
    BOT_CHANNELS,
    bot_manager,
    create_adapter,
    deliver_outgoing,
    find_or_create_chat,
    get_config,
    get_configs,
    start_bots,
    stop_bots,
    store_incoming,
    upsert_config,
)

__all__ = [
    "BOT_CHANNELS",
    "CHANNEL_MAKS",
    "CHANNEL_TELEGRAM",
    "BotAdapter",
    "IncomingMessage",
    "bot_manager",
    "create_adapter",
    "deliver_outgoing",
    "find_or_create_chat",
    "get_config",
    "get_configs",
    "start_bots",
    "stop_bots",
    "store_incoming",
    "upsert_config",
]
