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


# HTML-мост Telegram Web App: читает initData из SDK и пересылает на /shop/mini.
# Telegram передаёт initData не в URL, а через window.Telegram.WebApp.initData,
# поэтому нужен этот промежуточный шаг. Указать этот URL в BotFather как Web App.
_MINI_LAUNCH_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UWU</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:#070b16; color:#e8edf9; font-family:-apple-system,"Segoe UI",Roboto,sans-serif; }
  .box { text-align:center; padding:24px; }
  .mark { width:56px; height:56px; border-radius:16px; margin:0 auto 16px;
          background:linear-gradient(135deg,#7c9cff,#4ee0c0); display:grid; place-items:center;
          font-weight:800; font-size:24px; color:#0a1020; }
  .spinner { width:22px; height:22px; margin:12px auto 0; border:2px solid rgba(126,150,200,.3);
             border-top-color:#7c9cff; border-radius:50%; animation:spin 0.8s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  .muted { color:#97a4c0; font-size:13px; margin-top:10px; }
</style>
</head>
<body>
  <div class="box">
    <div class="mark">U</div>
    <div id="status">Открытие магазина…</div>
    <div class="spinner"></div>
    <div class="muted" id="hint"></div>
  </div>
  <script>
    (function () {
      var status = document.getElementById('status');
      var hint = document.getElementById('hint');
      if (!window.Telegram || !window.Telegram.WebApp) {
        status.textContent = 'Откройте Mini App из Telegram';
        hint.textContent = 'Этот адрес предназначен для кнопки меню бота.';
        return;
      }
      Telegram.WebApp.ready();
      var initData = Telegram.WebApp.initData || '';
      if (!initData) {
        status.textContent = 'Не удалось получить данные Telegram';
        return;
      }
      window.location.replace('/shop/mini?channel=telegram&initData=' + encodeURIComponent(initData));
    })();
  </script>
</body>
</html>"""


@router.get("/mini/launch", response_class=HTMLResponse)
async def mini_launch():
    """Мост Telegram Web App (укажите этот URL в BotFather как Web App)."""
    return HTMLResponse(_MINI_LAUNCH_HTML)
