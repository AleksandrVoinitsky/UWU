"""Зависимости аутентификации покупателя.

Покупатель аутентифицируется отдельным JWT (``type="customer"``) из cookie
``customer_token`` или заголовка ``Authorization: Bearer``. Токены сотрудников
(``type="user"``) здесь не принимаются.

См. также: :mod:`app.core.security`, :mod:`app.services.customer_service`.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_customer_token
from app.models.customer import Customer
from app.services import customer_service

CUSTOMER_TOKEN_COOKIE = "customer_token"


async def get_current_customer(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Customer:
    """Возвращает покупателя из cookie или Bearer-токена."""
    token = request.cookies.get(CUSTOMER_TOKEN_COOKIE)
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[len("Bearer "):]
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не аутентифицирован",
        )
    customer_id = decode_customer_token(token)
    if customer_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен",
        )
    customer = await customer_service.get_customer(session, customer_id)
    if customer is None or not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Аккаунт недоступен",
        )
    return customer


async def get_current_customer_optional(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Customer | None:
    """Покупатель или ``None`` (для страниц, доступных без входа)."""
    try:
        return await get_current_customer(request, session)
    except HTTPException:
        return None
