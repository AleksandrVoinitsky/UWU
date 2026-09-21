"""Сервис справочников (НСИ) и констант.

Предоставляет универсальные операции CRUD поверх ORM-моделей справочников, а
также специфичную логику (автогенерация кодов номенклатуры и контрагентов,
работа с константами).

См. также: :mod:`app.models.catalog`, :mod:`app.models.constants`.
"""
from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.catalog import Kontragent, Nomenklatura
from app.models.constants import DEFAULT_CONSTANTS, Constant

ModelT = TypeVar("ModelT", bound=Base)


async def list_all(session: AsyncSession, model: type[ModelT]) -> list[ModelT]:
    result = await session.execute(select(model).order_by(model.id))  # type: ignore[attr-defined]
    return list(result.scalars())


async def get_one(session: AsyncSession, model: type[ModelT], obj_id: int) -> ModelT | None:
    return await session.get(model, obj_id)


async def create_one(session: AsyncSession, model: type[ModelT], **fields: Any) -> ModelT:
    obj = model(**fields)
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def update_one(
    session: AsyncSession, obj: ModelT, **fields: Any
) -> ModelT:
    for key, value in fields.items():
        if value is not None:
            setattr(obj, key, value)
    await session.commit()
    await session.refresh(obj)
    return obj


async def delete_one(session: AsyncSession, obj: ModelT) -> None:
    await session.delete(obj)
    await session.commit()


async def next_code(session: AsyncSession, model: type[Any], prefix: str = "") -> str:
    """Генерирует следующий числовой код справочника (001, 002, ...)."""
    max_code = await session.execute(select(func.max(model.code)))
    current = max_code.scalar() or "0"
    # Извлекаем числовую часть (если код числовой).
    try:
        number = int(current)
    except (TypeError, ValueError):
        number = 0
    return prefix + str(number + 1).zfill(3)


async def next_nomenklatura_code(session: AsyncSession) -> str:
    return await next_code(session, Nomenklatura, "")


async def next_kontragent_code(session: AsyncSession) -> str:
    return await next_code(session, Kontragent, "")


# --- Константы ---


async def get_constants(session: AsyncSession) -> dict[str, Any]:
    """Возвращает все константы (со значениями по умолчанию)."""
    result = await session.execute(select(Constant))
    stored = {c.key: c.value for c in result.scalars()}
    merged = {**DEFAULT_CONSTANTS, **stored}
    return merged


async def set_constant(session: AsyncSession, key: str, value: Any) -> None:
    result = await session.execute(select(Constant).where(Constant.key == key))
    constant = result.scalar_one_or_none()
    if constant is None:
        constant = Constant(key=key, value=value)
        session.add(constant)
    else:
        constant.value = value
    await session.commit()
