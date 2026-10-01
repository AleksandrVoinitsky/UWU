"""Уведомление AI-агента о новых входящих сообщениях (webhook).

Когда в чате с ``Chat.agent_enabled=true`` приходит входящее сообщение
(покупатель сайта или бот), ядро отправляет webhook на ``POST /webhook``
отдельного сервиса ``uwu-ai-agent`` (см. :mod:`app.core.config` →
``agent_webhook_url``). Агент обрабатывает сообщение графом и публикует ответ
обратно через ``POST /api/agent/messages``.

Уведомление — best-effort: не блокирует сохранение сообщения и не роняет поток
при недоступности агента (ошибка логируется).

См. также: :mod:`app.bots.service`, :mod:`app.services.chat_service`,
:mod:`app.core.config`.
"""
from __future__ import annotations

import asyncio

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("app.agent_notify")


def is_enabled() -> bool:
    """Настроено ли уведомление агента (задан ли webhook URL)."""
    return bool(settings.agent_webhook_url)


async def _post_webhook(
    chat_id: int,
    text: str,
    *,
    channel: str,
    customer_id: int | None,
    message_id: int | None,
) -> None:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "channel": channel,
        "customer_id": customer_id,
        # message_id позволяет агенту дедуплицировать webhook против polling
        # (иначе одно входящее обрабатывается дважды).
        "message_id": message_id,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.agent_webhook_timeout) as client:
            resp = await client.post(settings.agent_webhook_url, json=payload)
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — агент может быть недоступен
        logger.warning("Не удалось уведомить AI-агента о сообщении (chat %s): %s", chat_id, exc)


def notify_agent(
    chat_id: int,
    text: str,
    *,
    channel: str,
    customer_id: int | None = None,
    message_id: int | None = None,
) -> None:
    """Запускает best-effort уведомление агента (fire-and-forget).

    Не требует ``await`` от вызывающего: создаёт фоновую задачу, чтобы не
    задерживать сохранение сообщения. При отсутствии webhook-URL — no-op.
    """
    if not is_enabled():
        return
    asyncio.create_task(
        _post_webhook(chat_id, text, channel=channel, customer_id=customer_id, message_id=message_id)
    )
