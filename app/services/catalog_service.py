"""Сервис справочников (НСИ) и констант.

Предоставляет универсальные операции CRUD поверх ORM-моделей справочников, а
также специфичную логику (автогенерация кодов номенклатуры и контрагентов,
работа с константами).

См. также: :mod:`app.models.catalog`, :mod:`app.models.constants`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, TypeVar

from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.catalog import CurrencyRate, Kontragent, Nomenklatura
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
    """Генерирует следующий числовой код справочника (001, 002, ...).

    Максимум считается по числовому значению кода (cast в Integer) только среди
    числовых кодов. Строковый максимум после перехода 999 → 1000 вернул бы
    «999» и снова сгенерировал «1000» (дубль уникального кода); при этом пустые
    и нечисловые коды (например «» или «ABC») игнорируются.
    """
    max_code = await session.execute(
        select(func.max(func.cast(model.code, Integer))).where(  # type: ignore[attr-defined]
            model.code.op("~")(r"^\d+$")  # только чисто числовые коды
        )
    )
    number = max_code.scalar() or 0
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


# --- Курсы валют (периодические) ---


async def get_latest_rate(
    session: AsyncSession, currency_id: int, on_date: date | None = None
) -> Decimal | None:
    """Курс валюты на дату (последний курс ≤ даты)."""
    target = on_date or date.today()
    result = await session.execute(
        select(CurrencyRate)
        .where(CurrencyRate.currency_id == currency_id, CurrencyRate.on_date <= target)
        .order_by(CurrencyRate.on_date.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row.rate if row else None


async def set_rate(
    session: AsyncSession,
    currency_id: int,
    on_date: date,
    rate: Decimal,
    multiplicity: int = 1,
) -> None:
    """Устанавливает (или обновляет) курс валюты на дату."""
    result = await session.execute(
        select(CurrencyRate).where(
            CurrencyRate.currency_id == currency_id,
            CurrencyRate.on_date == on_date,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        session.add(
            CurrencyRate(currency_id=currency_id, on_date=on_date, rate=rate, multiplicity=multiplicity)
        )
    else:
        row.rate = rate
        row.multiplicity = multiplicity
    await session.commit()
