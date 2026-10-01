"""Control-plane сервиса uwu-ai-agent (FastAPI).

Предоставляет ``/healthz`` и ``/webhook`` (получение уведомления о новом
входящем от ядра), а также фоновый polling ``/api/agent/inbox`` (если включён).
Полученное сообщение обрабатывается графом (:mod:`app.graph`), ответ публикуется
обратно в ядро через ``POST /api/agent/messages``.

См. также: :mod:`app.core_client`, :mod:`app.graph`, :mod:`app.llm`.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.core_client import CoreClient, CoreClientError
from app.graph import run_turn
from app.llm import LLM

logger = logging.getLogger("app.main")


class WebhookPayload(BaseModel):
    """Полезная нагрузка webhook-уведомления от ядра (чат + текст)."""

    chat_id: int
    text: str = ""
    channel: str = "internal"
    customer_id: int | None = None
    # Идентификатор сообщения в ядре — для дедупликации против polling.
    message_id: int | None = None


# Сообщения, обработанные или обрабатываемые сейчас (по message_id). Нужно,
# чтобы webhook и polling не обработали одно входящее дважды (гонка «webhook уже
# взял — polling ещё не увидел is_read»). При сбое занятие снимается (_release),
# чтобы polling повторил; при успехе id остаётся (память растёт с числом
# сообщений — приемлемо для демо, для прод-масштаба заменить на Redis/Postgres).
_claimed: set[int] = set()
_claim_lock = asyncio.Lock()


async def _claim(message_id: int) -> bool:
    """Атомарно занимает сообщение; False — его уже обрабатывает другой путь."""
    async with _claim_lock:
        if message_id in _claimed:
            return False
        _claimed.add(message_id)
        return True


async def _release(message_id: int) -> None:
    """Снимает занятие сообщения (при сбое — чтобы polling мог повторить)."""
    async with _claim_lock:
        _claimed.discard(message_id)


def _to_message_id(value: Any) -> int:
    """Приводит message_id к int; невалидный → -1 (дедупликация не применяется)."""
    try:
        mid = int(value)
    except (TypeError, ValueError):
        return -1
    return mid if mid > 0 else -1


async def _process_message(client: CoreClient, llm: LLM, message: dict[str, Any]) -> None:
    """Обрабатывает одно входящее сообщение: граф → ответ → аудит."""
    mid = _to_message_id(message.get("message_id"))

    # Дедупликация webhook ↔ polling: одно сообщение обрабатываем один раз.
    if mid > 0 and not await _claim(mid):
        logger.info("skip already-claimed message id=%s", mid)
        return

    try:
        state = await run_turn(client, llm, message)
    except Exception:  # noqa: BLE001 — при сбое снимаем занятие, чтобы повторить
        if mid > 0:
            await _release(mid)
        raise

    if not state.final_answer:
        if mid > 0:
            await client.mark_inbox_read([mid])
        return

    try:
        await client.post_message(state.chat_id, state.final_answer)
        if mid > 0:
            await client.mark_inbox_read([mid])
    except CoreClientError as exc:
        logger.warning("failed to post reply to chat %s: %s", state.chat_id, exc)
        if mid > 0:
            await _release(mid)  # не ответили — разрешаем повторную попытку
        return

    await client.post_run(
        trace_id=state.trace_id,
        chat_id=state.chat_id,
        customer_id=state.customer_id,
        intent=state.intent,
        tool_calls=state.tool_calls,
        status="ok",
        model=llm.model if llm.available else None,
    )


async def _polling_loop(client: CoreClient, llm: LLM) -> None:
    """Фоновый цикл: опрашивает /api/agent/inbox и обрабатывает сообщения."""
    logger.info("Polling loop started (interval=%ss)", settings.poll_interval)
    while True:
        try:
            inbox = await client.get_inbox()
            for message in inbox:
                try:
                    await _process_message(client, llm, message)
                except Exception as exc:  # noqa: BLE001 — одно сообщение не роняет цикл
                    # Не помечаем прочитанным: при сбое _process_message снял
                    # занятие, и polling повторит попытку на следующем цикле.
                    logger.exception("failed to process message %s: %s", message.get("message_id"), exc)
        except CoreClientError as exc:
            logger.warning("polling inbox failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("polling loop error: %s", exc)
        await asyncio.sleep(settings.poll_interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Запускает фоновый polling и останавливает его при завершении."""
    logger.info("Starting %s", settings.app_name)
    client = CoreClient()
    llm = LLM()
    app.state.client = client
    app.state.llm = llm

    task: asyncio.Task | None = None
    if settings.enable_polling:
        task = asyncio.create_task(_polling_loop(client, llm))

    yield

    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await client.aclose()
    logger.info("%s stopped", settings.app_name)


def create_app() -> FastAPI:
    application = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    @application.get("/healthz", tags=["health"])
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok", "service": settings.app_name})

    @application.post("/webhook")
    async def webhook(payload: WebhookPayload) -> JSONResponse:
        """Уведомление от ядра о новом входящем (best-effort, асинхронно)."""
        client: CoreClient = application.state.client
        llm: LLM = application.state.llm
        # message_id из payload участвует в дедупликации против polling.
        asyncio.create_task(_process_message(client, llm, payload.model_dump()))
        return JSONResponse({"status": "accepted"})

    return application


app = create_app()
