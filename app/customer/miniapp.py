"""MiniApp: вход через initData мессенджера (Telegram/MAX).

Точка входа ``/mini`` принимает подписанный ``initData``, проверяет подпись,
связывает пользователя мессенджера с покупателем (авто-создание при первом
входе) и переадресует на каталог ``/shop/``. Дальше MiniApp переиспользует тот
же REST API и страницы, что и клиентский сайт.

В режиме разработки (``MINIAPP_DEV=true``) подпись не проверяется — принимаются
``channel``/``user_id``/``name`` напрямую (для локального тестирования).

См. также: :mod:`app.services.miniapp_service`, :mod:`app.customer.deps`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots.service import get_config
from app.core.config import settings
from app.core.database import get_session
from app.core.security import create_customer_token
from app.customer.deps import CUSTOMER_TOKEN_COOKIE
from app.services import miniapp_service

router = APIRouter(tags=["customer-miniapp"])


@router.get("/mini")
async def mini_entry(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    channel = request.query_params.get("channel") or miniapp_service.CHANNEL_TELEGRAM

    if settings.miniapp_dev:
        # Режим разработки: подпись не проверяется (для локальной отладки).
        if channel not in miniapp_service.VALID_CHANNELS:
            return HTMLResponse("Неизвестный канал", status_code=400)
        external_id = request.query_params.get("user_id")
        name = request.query_params.get("name") or ""
        if not external_id:
            return HTMLResponse("Не указан user_id", status_code=400)
        info = {"channel": channel, "external_id": external_id, "name": name}
    else:
        init_data = (
            request.query_params.get("initData")
            or request.query_params.get("tgWebAppData")
            or ""
        )
        cfg = await get_config(session, channel)
        if cfg is None or not cfg.token:
            return HTMLResponse("Бот не настроен для этого канала", status_code=400)
        info = miniapp_service.validate_init_data(channel, init_data, cfg.token)
        if info is None:
            return HTMLResponse("Неверная подпись initData", status_code=401)

    customer = await miniapp_service.find_or_create_customer(
        session, info["channel"], info["external_id"], info["name"]
    )
    response = RedirectResponse("/shop/", status_code=303)
    response.set_cookie(
        CUSTOMER_TOKEN_COOKIE,
        create_customer_token(customer.id),
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
    )
    return response
