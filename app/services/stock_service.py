"""Складской учёт: остатки, партии, себестоимость.

Реализует примитивы партионного учёта: приход формирует :class:`StockBatch`,
расход списывает по выбранному методу (FIFO/LIFO/средняя) и возвращает
себестоимость. Остатки — сумма остатков партий.

См. также: :mod:`app.models.registry`, :mod:`app.models.enums.CostMethod`,
:mod:`app.services.document_service`.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CostMethod
from app.models.registry import StockBatch, StockMovement


@dataclass
class ConsumedLine:
    """Результат списания из одной партии."""

    batch_id: int
    quantity: Decimal
    unit_cost: Decimal

    @property
    def amount(self) -> Decimal:
        return self.quantity * self.unit_cost


async def get_balance(
    session: AsyncSession, nomenklatura_id: int, sklad_id: int | None = None
) -> Decimal:
    """Остаток номенклатуры (по складу или суммарно)."""
    stmt = select(func.coalesce(func.sum(StockBatch.quantity), 0)).where(
        StockBatch.nomenklatura_id == nomenklatura_id
    )
    if sklad_id is not None:
        stmt = stmt.where(StockBatch.sklad_id == sklad_id)
    result = await session.execute(stmt)
    return result.scalar() or Decimal("0")


async def get_balances(
    session: AsyncSession, sklad_id: int | None = None
) -> list[tuple[int, int, Decimal]]:
    """Остатки по всем позициям: [(nomenklatura_id, sklad_id, qty), ...]."""
    stmt = select(
        StockBatch.nomenklatura_id,
        StockBatch.sklad_id,
        func.sum(StockBatch.quantity),
    ).group_by(StockBatch.nomenklatura_id, StockBatch.sklad_id)
    if sklad_id is not None:
        stmt = stmt.where(StockBatch.sklad_id == sklad_id)
    result = await session.execute(stmt)
    return [(r[0], r[1], r[2]) for r in result.all()]


async def create_incoming(
    session: AsyncSession,
    *,
    document_id: int,
    date,
    nomenklatura_id: int,
    sklad_id: int,
    quantity: Decimal,
    price: Decimal,
) -> StockBatch:
    """Оприходует партию и регистрирует движение прихода."""
    batch = StockBatch(
        nomenklatura_id=nomenklatura_id,
        sklad_id=sklad_id,
        quantity=quantity,
        unit_cost=price,
        source_document_id=document_id,
    )
    session.add(batch)
    await session.flush()  # получаем batch.id

    movement = StockMovement(
        document_id=document_id,
        date=date,
        nomenklatura_id=nomenklatura_id,
        sklad_id=sklad_id,
        quantity=quantity,
        amount=quantity * price,
        batch_id=batch.id,
    )
    session.add(movement)
    return batch


async def consume_batches(
    session: AsyncSession,
    *,
    nomenklatura_id: int,
    sklad_id: int,
    quantity: Decimal,
    method: CostMethod,
) -> tuple[list[ConsumedLine], Decimal]:
    """Списывает ``quantity`` по методу себестоимости.

    Возвращает (строки списания по партиям, общая себестоимость).

    Возбуждает :class:`InsufficientStockError`, если остатка не хватает.
    """
    stmt = select(StockBatch).where(
        StockBatch.nomenklatura_id == nomenklatura_id,
        StockBatch.sklad_id == sklad_id,
        StockBatch.quantity > 0,
    )
    if method == CostMethod.LIFO:
        stmt = stmt.order_by(StockBatch.id.desc())
    else:  # FIFO и средняя списывают в порядке поступления
        stmt = stmt.order_by(StockBatch.id.asc())
    result = await session.execute(stmt)
    batches = list(result.scalars())

    total_available = sum((b.quantity for b in batches), Decimal("0"))
    if total_available < quantity:
        raise InsufficientStockError(
            nomenklatura_id=nomenklatura_id,
            sklad_id=sklad_id,
            available=total_available,
            required=quantity,
        )

    if method == CostMethod.AVERAGE:
        total_cost = sum((b.quantity * b.unit_cost for b in batches), Decimal("0"))
        avg_cost = (total_cost / total_available).quantize(Decimal("0.0001"))

    remaining = quantity
    consumed: list[ConsumedLine] = []
    for batch in batches:
        if remaining <= 0:
            break
        take = min(batch.quantity, remaining)
        if method == CostMethod.AVERAGE:
            unit_cost = avg_cost
        else:
            unit_cost = batch.unit_cost
        batch.quantity -= take
        consumed.append(ConsumedLine(batch.id, take, unit_cost))
        remaining -= take

    total_amount = sum((c.amount for c in consumed), Decimal("0"))
    return consumed, total_amount


async def register_outgoing(
    session: AsyncSession,
    *,
    document_id: int,
    date,
    nomenklatura_id: int,
    sklad_id: int,
    quantity: Decimal,
    amount: Decimal,
) -> None:
    """Регистрирует движение расхода (без изменения партий)."""
    movement = StockMovement(
        document_id=document_id,
        date=date,
        nomenklatura_id=nomenklatura_id,
        sklad_id=sklad_id,
        quantity=-quantity,
        amount=-amount,
    )
    session.add(movement)


class InsufficientStockError(Exception):
    """Недостаточно остатка при списании (контроль остатков)."""

    def __init__(self, nomenklatura_id: int, sklad_id: int, available: Decimal, required: Decimal):
        self.nomenklatura_id = nomenklatura_id
        self.sklad_id = sklad_id
        self.available = available
        self.required = required
        super().__init__(
            f"Insufficient stock for item {nomenklatura_id} on warehouse {sklad_id}: "
            f"available {available}, required {required}"
        )
