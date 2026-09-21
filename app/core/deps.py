"""FastAPI-зависимости (аутентификация, права доступа).

См. также: :mod:`app.core.security`, :mod:`app.models.users`.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.core.security import decode_access_token
from app.models.users import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def _load_user(session: AsyncSession, user_id: int) -> User | None:
    """Загружает пользователя с ролью (для проверки прав без lazy-load)."""
    result = await session.execute(
        select(User).options(selectinload(User.role)).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Возвращает текущего пользователя из Bearer-токена."""
    if not token:
        raise _CREDENTIALS_ERROR
    subject = decode_access_token(token)
    if subject is None:
        raise _CREDENTIALS_ERROR
    user = await _load_user(session, int(subject))
    if user is None or not user.is_active:
        raise _CREDENTIALS_ERROR
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Пропускает только администраторов."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )
    return user


async def get_current_user_optional(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Возвращает пользователя из cookie-токена (для веб-интерфейса) или None."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    subject = decode_access_token(token)
    if subject is None:
        return None
    user = await _load_user(session, int(subject))
    if user is None or not user.is_active:
        return None
    return user


async def get_current_user_from_cookie(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Требует аутентификации по cookie-токену (для веб-интерфейса).

    При отсутствии валидной сессии перенаправляет на страницу входа.
    """
    user = await get_current_user_optional(request, session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return user
