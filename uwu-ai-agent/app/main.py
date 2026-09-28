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


async def _process_message(client: CoreClient, llm: LLM, message: dict[str, Any]) -> None:
    """Обрабатывает одно входящее сообщение: граф → ответ → аудит."""
    state = await run_turn(client, llm, message)
    if not state.final_answer:
        await client.mark_inbox_read([int(message["message_id"])])
        return

    try:
        await client.post_message(state.chat_id, state.final_answer)
    except CoreClientError as exc:
        logger.warning("failed to post reply to chat %s: %s", state.chat_id, exc)
    finally:
        await client.mark_inbox_read([int(message["message_id"])])

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
                    logger.exception("failed to process message %s: %s", message.get("message_id"), exc)
                    await client.mark_inbox_read([int(message["message_id"])])
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
        message = payload.model_dump()
        message["message_id"] = -1  # webhook не несёт message_id (не polling)
        asyncio.create_task(_process_message(client, llm, message))
        return JSONResponse({"status": "accepted"})

    return application


app = create_app()
