"""Веб-страница входа.

Единый экран входа по логину/паролю. После входа администратор попадает в
админку, остальные пользователи — в торговый интерфейс.

См. также: :mod:`app.services.auth_service`, :mod:`app.web.admin`,
:mod:`app.web.trade`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.i18n import translate
from app.services.auth_service import AuthError, authenticate

router = APIRouter(tags=["web-auth"])


def _lang(request: Request) -> str:
    return request.cookies.get("lang") or settings.default_language


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render_login(request, None)


@router.post("/login")
async def login_submit(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    try:
        token = await authenticate(session, login, password)
    except AuthError:
        return _render_login(request, translate("auth.invalid", _lang(request)))

    from app.services.auth_service import get_user_by_login

    user = await get_user_by_login(session, login)
    response = RedirectResponse(
        url="/admin" if (user and user.is_admin) else "/", status_code=303
    )
    response.set_cookie("access_token", token, httponly=True, samesite="lax")
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response


@router.get("/set-language/{lang}")
async def set_language(lang: str, request: Request):
    """Переключает язык интерфейса (cookie `lang`)."""
    from app.core.i18n import SUPPORTED_LANGUAGES

    target = lang if lang in SUPPORTED_LANGUAGES else "ru"
    referer = request.headers.get("referer") or "/"
    response = RedirectResponse(url=referer, status_code=303)
    response.set_cookie("lang", target, samesite="lax")
    return response


def _render_login(request: Request, error: str | None) -> HTMLResponse:
    from app.core.config import settings as s
    from app.templates import render

    lang = _lang(request)
    return HTMLResponse(
        render(
            "login.html",
            error=error,
            lang=lang,
            app_name=s.app_name,
            t=translate,
        )
    )
