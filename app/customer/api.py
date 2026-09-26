"""REST API покупателя (переиспользуется сайтом и MiniApp).

Маршруты монтируются под ``/shop``: ``/shop/api/...``. Аутентификация — JWT
покупателя (``type="customer"``).

См. также: :mod:`app.services.customer_service`, :mod:`app.customer.deps`.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import create_customer_token
from app.customer.deps import CUSTOMER_TOKEN_COOKIE, get_current_customer
from app.models.customer import Customer
from app.services import chat_service, customer_service, pdf_service
from app.services.customer_service import CustomerAuthError, CustomerError

router = APIRouter(prefix="/api", tags=["customer"])


# --- Схемы ---


class RegisterRequest(BaseModel):
    phone: str
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    phone: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CartAddRequest(BaseModel):
    nomenklatura_id: int
    quantity: Decimal


class CartUpdateRequest(BaseModel):
    quantity: Decimal


class ChatMessageRequest(BaseModel):
    text: str


# --- Аутентификация ---


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: AsyncSession = Depends(get_session)):
    try:
        customer = await customer_service.register(
            session, payload.phone, payload.password, payload.name
        )
    except CustomerError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"access_token": create_customer_token(customer.id), "token_type": "bearer"}


@router.post("/login")
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_session)):
    try:
        customer = await customer_service.authenticate(session, payload.phone, payload.password)
    except CustomerAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return {"access_token": create_customer_token(customer.id), "token_type": "bearer"}


@router.get("/me")
async def me(customer: Customer = Depends(get_current_customer)):
    return {"id": customer.id, "phone": customer.phone, "name": customer.name}


# --- Каталог ---


@router.get("/categories")
async def categories(session: AsyncSession = Depends(get_session)):
    cats = await customer_service.list_categories(session)
    return [
        {"id": c.id, "name": c.name, "parent_id": c.parent_id} for c in cats
    ]


@router.get("/products")
async def products(
    category_id: int | None = Query(default=None),
    search: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    return await customer_service.available_products(session, category_id, search)


# --- Корзина ---


@router.get("/cart")
async def cart(
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    items = await customer_service.get_cart_items(session, customer.id)
    return {"items": items, "total": await customer_service.cart_total(session, customer.id)}


@router.post("/cart", status_code=status.HTTP_201_CREATED)
async def cart_add(
    payload: CartAddRequest,
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    try:
        await customer_service.add_to_cart(
            session, customer.id, payload.nomenklatura_id, payload.quantity
        )
    except CustomerError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return await cart(session=session, customer=customer)


@router.patch("/cart/{item_id}")
async def cart_update(
    item_id: int,
    payload: CartUpdateRequest,
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    try:
        await customer_service.set_cart_quantity(session, customer.id, item_id, payload.quantity)
    except CustomerError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return await cart(session=session, customer=customer)


# --- Заказы ---


@router.post("/checkout", status_code=status.HTTP_201_CREATED)
async def checkout(
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    try:
        doc = await customer_service.checkout(session, customer)
    except CustomerError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return await customer_service.order_context(session, doc)


@router.get("/orders")
async def orders(
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    docs = await customer_service.list_customer_orders(session, customer.id)
    return [
        {"id": d.id, "number": d.number, "date": d.date.isoformat(), "total": d.total}
        for d in docs
    ]


@router.get("/orders/{order_id}")
async def order_detail(
    order_id: int,
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    doc = await customer_service.get_customer_order(session, customer.id, order_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")
    return await customer_service.order_context(session, doc)


# --- Чат с продавцом ---


@router.get("/chat")
async def chat_messages(
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    return {"messages": await chat_service.list_customer_messages(session, customer)}


@router.post("/chat", status_code=status.HTTP_201_CREATED)
async def chat_send(
    payload: ChatMessageRequest,
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пустое сообщение")
    if len(text) > 4000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Сообщение слишком длинное")
    return await chat_service.send_customer_message(session, customer, text)


@router.get("/orders/{order_id}/pdf")
async def order_pdf(
    order_id: int,
    session: AsyncSession = Depends(get_session),
    customer: Customer = Depends(get_current_customer),
):
    doc = await customer_service.get_customer_order(session, customer.id, order_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")
    ctx = await customer_service.order_context(session, doc)
    try:
        pdf_bytes = pdf_service.render_order_pdf(ctx)
    except Exception as exc:  # noqa: BLE001 — WeasyPrint может быть недоступен
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось сформировать PDF: {exc}",
        ) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="order-{doc.number}.pdf"'},
    )
