"""Веб-интерфейс администратора.

Администратор не видит торговый интерфейс: здесь — управление пользователями,
ролями/правами, настройками (константы) и документацией.

См. также: :mod:`app.services.user_service`, :mod:`app.web.docs`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user_from_cookie
from app.core.i18n import translate
from app.models.registry import AuditLog
from app.models.users import PERMISSIONS, User
from app.models.catalog import Valyuta
from app.schemas.auth import UserCreate
from app.services import catalog_service, user_service
from app.templates import render

router = APIRouter(tags=["web-admin"])


def _lang(request: Request) -> str:
    return request.cookies.get("lang") or "ru"


def _page(request: Request, user: User, template: str, **ctx) -> HTMLResponse:
    lang = _lang(request)
    return HTMLResponse(
        render(
            template,
            lang=lang,
            t=translate,
            user=user,
            section="admin",
            **ctx,
        )
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    users = await user_service.list_users(session)
    roles = await user_service.list_roles(session)
    return _page(request, user, "admin/dashboard.html", users=users, roles=roles)


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    users = await user_service.list_users(session)
    roles = await user_service.list_roles(session)
    return _page(request, user, "admin/users.html", users=users, roles=roles)


@router.post("/admin/users", response_class=HTMLResponse)
async def admin_create_user(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
    email: str = Form(""),
    role_id: str = Form(""),
    is_admin: str = Form(""),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    await user_service.create_user(
        session,
        login=login,
        password=password,
        full_name=full_name or None,
        email=email or None,
        is_admin=is_admin == "on",
        role_id=int(role_id) if role_id else None,
    )
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/delete")
async def admin_delete_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    target = await user_service.get_user(session, user_id)
    if target and not target.is_admin and target.id != user.id:
        await user_service.delete_user(session, target)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/toggle")
async def admin_toggle_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    target = await user_service.get_user(session, user_id)
    if target and target.id != user.id:
        await user_service.update_user(session, target, is_active=not target.is_active)
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/admin/roles", response_class=HTMLResponse)
async def admin_roles(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    roles = await user_service.list_roles(session)
    return _page(request, user, "admin/roles.html", roles=roles, permissions=PERMISSIONS)


@router.post("/admin/roles/{role_id}/permissions")
async def admin_update_role(
    role_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    selected = [k for k in form.keys() if k.startswith("perm_")]
    permissions = [k[len("perm_"):] for k in selected]
    role = await user_service.get_role(session, role_id)
    if role:
        await user_service.update_role(session, role, name=None, permissions=permissions)
    return RedirectResponse("/admin/roles", status_code=303)


@router.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    constants = await catalog_service.get_constants(session)
    valyuty = await catalog_service.list_all(session, Valyuta)
    return _page(request, user, "admin/settings.html", constants=constants, valyuty=valyuty)


@router.post("/admin/settings")
async def admin_save_settings(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    # Чекбоксы: отсутствуют в форме, если сняты — явно сбрасываем в False.
    for checkbox_key in ("allow_future_dates", "enforce_min_price"):
        await catalog_service.set_constant(
            session, checkbox_key, f"const_{checkbox_key}" in form
        )
    for key, value in form.items():
        if key.startswith("const_"):
            const_key = key[len("const_"):]
            if const_key in ("allow_future_dates", "enforce_min_price"):
                continue
            await catalog_service.set_constant(session, const_key, value)
    return RedirectResponse("/admin/settings", status_code=303)


@router.get("/admin/audit", response_class=HTMLResponse)
async def admin_audit(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    result = await session.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(200))
    logs = list(result.scalars())
    # Имена пользователей.
    user_map = {u.id: u.login for u in await user_service.list_users(session)}
    return _page(request, user, "admin/audit.html", logs=logs, user_map=user_map)


@router.get("/admin/bots", response_class=HTMLResponse)
async def admin_bots(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    from app.bots.service import BOT_CHANNELS, bot_manager, get_configs

    configs = {c.channel: c for c in await get_configs(session)}
    status = {ch: bot_manager.get(ch) is not None for ch in BOT_CHANNELS}
    return _page(
        request,
        user,
        "admin/bots.html",
        channels=BOT_CHANNELS,
        configs=configs,
        status=status,
    )


@router.post("/admin/bots", response_class=HTMLResponse)
async def admin_save_bots(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    from app.bots.service import BOT_CHANNELS, upsert_config

    form = await request.form()
    for channel in BOT_CHANNELS:
        enabled = form.get(f"{channel}_enabled") == "on"
        token = (form.get(f"{channel}_token") or "").strip() or None
        name = (form.get(f"{channel}_name") or "").strip() or None
        await upsert_config(
            session, channel, enabled=enabled, token=token, name=name
        )
    return RedirectResponse("/admin/bots", status_code=303)
