"""Асинхронный доступ к базе данных.

Использует SQLAlchemy 2.0 (async) поверх ``asyncpg``. Движок и фабрика сессий
создаются один раз и переиспользуются через :func:`get_session`.

См. также: :mod:`app.models.base`, :mod:`app.core.config`.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-зависимость: выдаёт сессию и закрывает её после запроса."""
    async with async_session_factory() as session:
        yield session
