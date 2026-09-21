"""Фикстуры pytest (интеграционные тесты с PostgreSQL).

Подключение к тестовой БД задаётся переменной ``TEST_DATABASE_URL`` (по
умолчанию — ``uwu_test`` на ``localhost:5433``).

На Windows asyncpg и SQLAlchemy привязывают соединения пула к event loop; чтобы
избежать ошибки «Future attached to a different loop», тестовый движок
пересоздаётся с ``NullPool`` (соединение создаётся и закрывается в одном цикле).

См. также: :mod:`app.core.database`, :mod:`app.services.seed_service`.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Должно быть установлено ДО импорта app.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://uwu:uwu@localhost:5433/uwu_test"
)

import app.core.database as db  # noqa: E402

# Пересоздаём движок с NullPool для тестов.
_test_engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
_test_session_factory = async_sessionmaker(
    bind=_test_engine, class_=db.AsyncSession, expire_on_commit=False
)
db.engine = _test_engine
db.async_session_factory = _test_session_factory

from app.core.database import Base  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.main import app  # noqa: E402
from app.services import seed_service  # noqa: E402

engine = _test_engine
async_session_factory = _test_session_factory


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _setup_db():
    """Создаёт схему БД один раз на сессию тестов."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture(autouse=True)
async def _clean_db():
    """Очищает все таблицы перед каждым тестом."""
    async with engine.begin() as conn:
        tables = ", ".join(Base.metadata.tables.keys())
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
async def session() -> AsyncGenerator:
    async with async_session_factory() as s:
        yield s


@pytest.fixture
async def seeded_session(session):
    """Сессия с начальными данными (роли, валюты, НДС, единицы, админ)."""
    await seed_service.seed_all(session)
    return session


@pytest.fixture
async def client() -> AsyncGenerator:
    """ASGI-клиент для тестов API."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def admin_token(seeded_session) -> str:
    """JWT администратора (создан сидом)."""
    user = await seeded_session.execute(
        text("SELECT id FROM users WHERE is_admin = TRUE LIMIT 1")
    )
    user_id = user.scalar()
    return create_access_token(str(user_id))


@pytest.fixture
async def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}
