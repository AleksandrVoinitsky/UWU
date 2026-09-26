"""Аутентификация: проверка учётных данных и выдача токена.

См. также: :mod:`app.core.security`, :mod:`app.models.users`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, verify_password
from app.models.users import User


class AuthError(Exception):
    """Неверные учётные данные."""


async def authenticate(session: AsyncSession, login: str, password: str) -> str:
    """Проверяет логин/пароль и возвращает JWT-токен.

    Возбуждает :class:`AuthError` при неверных данных или неактивной учётке.
    """
    user = await get_user_by_login(session, login)
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("Invalid login or password")
    if not user.is_active:
        raise AuthError("Account is disabled")
    user.last_login_at = datetime.now(timezone.utc)
    await session.commit()
    return create_access_token(str(user.id))


async def get_user_by_login(session: AsyncSession, login: str) -> User | None:
    result = await session.execute(select(User).where(User.login == login))
    return result.scalar_one_or_none()
