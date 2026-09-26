"""Инициализация начальных данных (сид).

Создаёт администратора (из переменных окружения), встроенные роли, базовые
валюты, ставки НДС и единицы измерения. Идемпотентно.

См. также: :mod:`app.core.config`, :mod:`app.services.user_service`.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.catalog import Edinitsa, StavkaNDS, Valyuta
from app.models.users import Role, User
from app.services.user_service import seed_default_roles

_DEFAULT_CURRENCIES = [
    ("RUB", "Российский рубль"),
    ("USD", "Доллар США"),
    ("EUR", "Евро"),
]

_DEFAULT_NDS = [
    ("Без НДС", "0"),
    ("НДС 20%", "20"),
    ("НДС 10%", "10"),
    ("НДС 0%", "0"),
]

_DEFAULT_UNITS = [
    ("штука", "шт"),
    ("килограмм", "кг"),
    ("литр", "л"),
    ("метр", "м"),
]


async def seed_all(session: AsyncSession) -> None:
    """Заполняет базу начальными данными (идемпотентно)."""
    await seed_roles(session)
    await seed_currencies(session)
    await seed_nds(session)
    await seed_units(session)
    await seed_admin(session)
    await seed_agent_defaults(session)
    await session.commit()


async def seed_agent_defaults(session: AsyncSession) -> None:
    """Дефолтные промпты и инструменты AI-агента (ленивый импорт — избегаем циклов)."""
    from app.services.agent_service import seed_agent

    await seed_agent(session)


async def seed_roles(session: AsyncSession) -> None:
    await seed_default_roles(session)


async def seed_currencies(session: AsyncSession) -> None:
    for code, name in _DEFAULT_CURRENCIES:
        exists = await session.execute(select(Valyuta).where(Valyuta.code == code))
        if exists.scalar_one_or_none() is None:
            session.add(Valyuta(code=code, name=name))


async def seed_nds(session: AsyncSession) -> None:
    for name, rate in _DEFAULT_NDS:
        exists = await session.execute(select(StavkaNDS).where(StavkaNDS.name == name))
        if exists.scalar_one_or_none() is None:
            session.add(StavkaNDS(name=name, rate=Decimal(rate)))


async def seed_units(session: AsyncSession) -> None:
    for name, short in _DEFAULT_UNITS:
        exists = await session.execute(select(Edinitsa).where(Edinitsa.short_name == short))
        if exists.scalar_one_or_none() is None:
            session.add(Edinitsa(name=name, short_name=short, coefficient=Decimal("1")))


async def seed_admin(session: AsyncSession) -> None:
    exists = await session.execute(select(User).where(User.is_admin.is_(True)))
    if exists.scalar_one_or_none() is not None:
        return
    admin_role = await session.execute(select(Role).where(Role.key == "admin"))
    role = admin_role.scalar_one_or_none()
    session.add(
        User(
            login=settings.admin_login,
            password_hash=hash_password(settings.admin_password),
            email=settings.admin_email,
            full_name="Administrator",
            is_active=True,
            is_admin=True,
            language=settings.default_language,
            role_id=role.id if role else None,
        )
    )
