"""Веб-интерфейс покупателя (серверный рендеринг).

Страницы: каталог, регистрация/вход, корзина, подтверждение заказа и PDF.
Переиспользует сервисы покупателя; та же логика доступна через REST API
(:mod:`app.customer.api`) для MiniApp.

См. также: :mod:`app.services.customer_service`, :mod:`app.customer.deps`.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.security import create_customer_token
from app.customer.deps import (
    CUSTOMER_TOKEN_COOKIE,
    get_current_customer,
    get_current_customer_optional,
)
from app.models.customer import Customer
from app.services import customer_service, site_service
from app.services.customer_service import CustomerError
from app.templates import render

router = APIRouter(tags=["customer-web"])

# Префикс, под которым клиентское приложение смонтировано в основном
# (для ссылок в шаблонах). Совпадает с mount("/shop", ...) в app/main.py.
SHOP_PREFIX = "/shop"


def _page(request: Request, template: str, customer: Customer | None = None, **ctx) -> HTMLResponse:
    return HTMLResponse(
        render(
            f"customer/{template}.html",
            customer=customer,
            prefix=SHOP_PREFIX,
            **ctx,
        )
    )


def _auth_redirect(response: RedirectResponse, token: str) -> RedirectResponse:
    response.set_cookie(
        CUSTOMER_TOKEN_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
    )
    return response


# --- Каталог (главная) ---


@router.get("/", response_class=HTMLResponse)
async def catalog_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    customer = await get_current_customer_optional(request, session)
    categories = await customer_service.list_categories(session)
    products = await customer_service.available_products(session)
    site_settings = await site_service.get_settings(session)
    return _page(
        request, "catalog",
        customer=customer, categories=categories, products=products,
        site_settings=site_settings,
    )


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_filtered(
    request: Request,
    category_id: int | None = None,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    customer = await get_current_customer_optional(request, session)
    categories = await customer_service.list_categories(session)
    products = await customer_service.available_products(session, category_id, search)
    site_settings = await site_service.get_settings(session)
    return _page(
        request, "catalog",
        customer=customer, categories=categories, products=products,
        category_id=category_id, search=search or "",
        site_settings=site_settings,
    )


# --- Регистрация / вход ---


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return _page(request, "login", customer=None, mode="register", error=None)


@router.post("/register")
async def register_submit(
    request: Request,
    phone: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
    name: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    if password != password2:
        return _page(request, "login", customer=None, mode="register", error="Пароли не совпадают")
    try:
        customer = await customer_service.register(session, phone, password, name or None)
    except CustomerError as exc:
        return _page(request, "login", customer=None, mode="register", error=str(exc))
    return _auth_redirect(RedirectResponse(f"{SHOP_PREFIX}/", status_code=303), create_customer_token(customer.id))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _page(request, "login", customer=None, mode="login", error=None)


@router.post("/login")
async def login_submit(
    request: Request,
    phone: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    try:
        customer = await customer_service.authenticate(session, phone, password)
    except CustomerError as exc:
        return _page(request, "login", customer=None, mode="login", error=str(exc))
    return _auth_redirect(RedirectResponse(f"{SHOP_PREFIX}/", status_code=303), create_customer_token(customer.id))


@router.get("/logout")
async def logout():
    response = RedirectResponse(f"{SHOP_PREFIX}/", status_code=303)
    response.delete_cookie(CUSTOMER_TOKEN_COOKIE)
    return response


# --- Корзина ---


@router.get("/cart", response_class=HTMLResponse)
async def cart_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    items = await customer_service.get_cart_items(session, customer.id)
    total = await customer_service.cart_total(session, customer.id)
    return _page(request, "cart", customer=customer, items=items, total=total)


@router.post("/cart/add")
async def cart_add(
    request: Request,
    nomenklatura_id: int = Form(...),
    quantity: Decimal = Form(...),
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    try:
        await customer_service.add_to_cart(session, customer.id, nomenklatura_id, quantity)
    except CustomerError:
        pass
    return RedirectResponse(f"{SHOP_PREFIX}/cart", status_code=303)


@router.post("/cart/update")
async def cart_update(
    request: Request,
    item_id: int = Form(...),
    quantity: Decimal = Form(...),
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    try:
        await customer_service.set_cart_quantity(session, customer.id, item_id, quantity)
    except CustomerError:
        pass
    return RedirectResponse(f"{SHOP_PREFIX}/cart", status_code=303)


# --- Заказы ---


@router.post("/checkout")
async def checkout(
    request: Request,
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    try:
        doc = await customer_service.checkout(session, customer)
    except CustomerError as exc:
        items = await customer_service.get_cart_items(session, customer.id)
        total = await customer_service.cart_total(session, customer.id)
        return _page(
            request, "cart", customer=customer, items=items, total=total, error=str(exc)
        )
    return RedirectResponse(f"{SHOP_PREFIX}/orders/{doc.id}", status_code=303)


@router.get("/orders", response_class=HTMLResponse)
async def orders_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    docs = await customer_service.list_customer_orders(session, customer.id)
    return _page(request, "orders", customer=customer, orders=docs)


@router.get("/orders/{order_id}", response_class=HTMLResponse)
async def order_page(
    request: Request,
    order_id: int,
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    doc = await customer_service.get_customer_order(session, customer.id, order_id)
    if doc is None:
        return HTMLResponse("Заказ не найден", status_code=404)
    ctx = await customer_service.order_context(session, doc)
    return _page(request, "order", customer=customer, order=ctx)


@router.get("/orders/{order_id}/pdf")
async def order_pdf(
    request: Request,
    order_id: int,
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    from fastapi.responses import Response

    doc = await customer_service.get_customer_order(session, customer.id, order_id)
    if doc is None:
        return HTMLResponse("Заказ не найден", status_code=404)
    ctx = await customer_service.order_context(session, doc)
    from app.services import pdf_service

    try:
        pdf_bytes = pdf_service.render_order_pdf(ctx)
    except Exception as exc:  # noqa: BLE001
        return HTMLResponse(f"Не удалось сформировать PDF: {exc}", status_code=500)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="order-{doc.number}.pdf"'},
    )
