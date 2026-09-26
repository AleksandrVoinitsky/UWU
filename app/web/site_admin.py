"""Веб-интерфейс управления клиентским сайтом/MiniApp (админка).

Управляет тем, что видит покупатель: логотип, рекламный баннер, оформление
карточек товаров, акции (скидки) и публикация товаров.

См. также: :mod:`app.services.site_service`, :mod:`app.models.site`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user_from_cookie
from app.core.i18n import translate
from app.models.catalog import Category, Nomenklatura
from app.models.site import DISCOUNT_TYPES
from app.models.users import User
from app.services import catalog_service, image_service, site_service
from app.templates import render

router = APIRouter(tags=["web-admin-site"])


def _lang(request: Request) -> str:
    return request.cookies.get("lang") or "ru"


def _page(request: Request, user: User, template: str, **ctx) -> HTMLResponse:
    return HTMLResponse(
        render(
            template,
            lang=_lang(request),
            t=translate,
            user=user,
            section="admin",
            **ctx,
        )
    )


async def _require_admin(user: User) -> bool:
    return not user.is_admin


def _as_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw.strip())
    except InvalidOperation:
        return None


def _as_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


# --- Обзор --------------------------------------------------------------------


@router.get("/admin/site", response_class=HTMLResponse)
async def site_admin(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if await _require_admin(user):
        return RedirectResponse("/", status_code=303)
    settings_ = await site_service.get_settings(session)
    promotions = await site_service.list_promotions(session)
    products = await catalog_service.list_all(session, Nomenklatura)
    categories = await catalog_service.list_all(session, Category)
    return _page(
        request,
        user,
        "admin/site.html",
        settings=settings_,
        promotions=promotions,
        products=products,
        categories=categories,
        discount_types=DISCOUNT_TYPES,
    )


# --- Настройки -----------------------------------------------------------------


@router.post("/admin/site/settings", response_class=HTMLResponse)
async def site_save_settings(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if await _require_admin(user):
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    values = {
        "card_style": form.get("card_style", "grid"),
        "banner_text": form.get("banner_text", ""),
        "banner_link": form.get("banner_link", ""),
        # Чекбоксы: отсутствуют в форме, если сняты.
        "banner_enabled": "banner_enabled" in form,
        "show_prices": "show_prices" in form,
        "show_description": "show_description" in form,
    }
    await site_service.set_settings(session, values)
    return RedirectResponse("/admin/site", status_code=303)


@router.post("/admin/site/logo", response_class=HTMLResponse)
async def site_upload_logo(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if await _require_admin(user):
        return RedirectResponse("/", status_code=303)
    filename = await image_service.save_image(file, "logo")
    if filename:
        await site_service.set_settings(session, {"logo_path": filename})
    return RedirectResponse("/admin/site", status_code=303)


@router.post("/admin/site/banner", response_class=HTMLResponse)
async def site_upload_banner(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if await _require_admin(user):
        return RedirectResponse("/", status_code=303)
    filename = await image_service.save_image(file, "banner")
    if filename:
        await site_service.set_settings(session, {"banner_image_path": filename})
    return RedirectResponse("/admin/site", status_code=303)


# --- Акции ---------------------------------------------------------------------


@router.post("/admin/site/promotions", response_class=HTMLResponse)
async def site_create_promotion(
    request: Request,
    name: str = Form(...),
    discount_type: str = Form("percent"),
    value: str = Form(...),
    description: str = Form(""),
    nomenklatura_id: str = Form(""),
    category_id: str = Form(""),
    starts_at: str = Form(""),
    ends_at: str = Form(""),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if await _require_admin(user):
        return RedirectResponse("/", status_code=303)
    val = _as_decimal(value)
    if name.strip() and val is not None:
        await site_service.create_promotion(
            session,
            name=name.strip(),
            discount_type=discount_type if discount_type in DISCOUNT_TYPES else "percent",
            value=val,
            description=description or None,
            nomenklatura_id=int(nomenklatura_id) if nomenklatura_id else None,
            category_id=int(category_id) if category_id else None,
            starts_at=_as_date(starts_at),
            ends_at=_as_date(ends_at),
        )
    return RedirectResponse("/admin/site", status_code=303)


@router.post("/admin/site/promotions/{promo_id}/toggle", response_class=HTMLResponse)
async def site_toggle_promotion(
    promo_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if await _require_admin(user):
        return RedirectResponse("/", status_code=303)
    promo = await site_service.get_promotion(session, promo_id)
    if promo:
        await site_service.update_promotion(session, promo, enabled=not promo.enabled)
    return RedirectResponse("/admin/site", status_code=303)


@router.post("/admin/site/promotions/{promo_id}/delete", response_class=HTMLResponse)
async def site_delete_promotion(
    promo_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if await _require_admin(user):
        return RedirectResponse("/", status_code=303)
    promo = await site_service.get_promotion(session, promo_id)
    if promo:
        await site_service.delete_promotion(session, promo)
    return RedirectResponse("/admin/site", status_code=303)


# --- Публикация товаров --------------------------------------------------------


@router.post("/admin/site/products/{product_id}/toggle", response_class=HTMLResponse)
async def site_toggle_product(
    product_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if await _require_admin(user):
        return RedirectResponse("/", status_code=303)
    product = await session.get(Nomenklatura, product_id)
    if product:
        product.is_published = not product.is_published
        await session.commit()
    return RedirectResponse("/admin/site", status_code=303)
