"""Ценообразование: закупочная цена, свободная цена, виды цен с наценкой.

Логика расчёта цены для пары (номенклатура, тип цен):

1. Явная цена из :class:`TsenaNomenklatury` (если задана).
2. Иначе — автонаценка: ``закупочная × (1 + наценка/100)``.
3. Иначе — ``None``.

Свободная цена (:attr:`Nomenklatura.retail_price`) используется для быстрых
продаж без видов цен (например, в РМК).

См. также: :mod:`app.models.catalog.nomenklatura`.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog.nomenklatura import Nomenklatura, TipTsen, TsenaNomenklatury


def auto_price(purchase_price: Decimal | None, markup_percent: Decimal | None) -> Decimal | None:
    """Автоматическая цена = закупочная × (1 + наценка/100)."""
    if purchase_price is None:
        return None
    markup = markup_percent or Decimal("0")
    return (purchase_price * (Decimal("1") + markup / Decimal("100"))).quantize(Decimal("0.01"))


async def get_explicit_prices(
    session: AsyncSession, nomenklatura_id: int
) -> dict[int, Decimal]:
    """Явные цены из справочника цен {tip_tsen_id: price}."""
    result = await session.execute(
        select(TsenaNomenklatury).where(TsenaNomenklatury.nomenklatura_id == nomenklatura_id)
    )
    return {p.tip_tsen_id: p.price for p in result.scalars()}


async def resolve_prices(
    session: AsyncSession,
    nomenklatura: Nomenklatura,
    tipy_tsen: list[TipTsen],
) -> dict[int, Decimal | None]:
    """Цена по каждому типу цен (явная или автонаценка)."""
    explicit = await get_explicit_prices(session, nomenklatura.id)
    result: dict[int, Decimal | None] = {}
    for tip in tipy_tsen:
        if tip.id in explicit:
            result[tip.id] = explicit[tip.id]
        else:
            result[tip.id] = auto_price(nomenklatura.purchase_price, tip.markup_percent)
    return result


async def set_explicit_price(
    session: AsyncSession,
    nomenklatura_id: int,
    tip_tsen_id: int,
    price: Decimal,
) -> None:
    """Задаёт (или перезаписывает) явную цену по типу цен."""
    result = await session.execute(
        select(TsenaNomenklatury).where(
            TsenaNomenklatury.nomenklatura_id == nomenklatura_id,
            TsenaNomenklatury.tip_tsen_id == tip_tsen_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        session.add(
            TsenaNomenklatury(
                nomenklatura_id=nomenklatura_id,
                tip_tsen_id=tip_tsen_id,
                price=price,
            )
        )
    else:
        row.price = price


async def clear_explicit_price(
    session: AsyncSession, nomenklatura_id: int, tip_tsen_id: int
) -> None:
    """Удаляет явную цену (возврат к автонаценке)."""
    await session.execute(
        delete(TsenaNomenklatury).where(
            TsenaNomenklatury.nomenklatura_id == nomenklatura_id,
            TsenaNomenklatury.tip_tsen_id == tip_tsen_id,
        )
    )
