"""Отчёты: остатки, движения, продажи, взаиморасчёты, деньги.

Все отчёты строятся агрегацией регистров. Возвращают списки словарей, готовых к
сериализации в JSON или отображению в шаблонах.

См. также: :mod:`app.models.registry`, :mod:`app.api.reports`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Kontragent, Nomenklatura, Sklad
from app.models.document.base_document import Document
from app.models.enums import DocType, DocumentStatus
from app.models.registry import (
    MoneyMovement,
    SettlementMovement,
    StockBatch,
    StockMovement,
)


async def stock_balances(session: AsyncSession) -> list[dict]:
    """Остатки товаров по складам."""
    stmt = (
        select(
            StockBatch.nomenklatura_id,
            StockBatch.sklad_id,
            func.sum(StockBatch.quantity),
            func.sum(StockBatch.quantity * StockBatch.unit_cost),
        )
        .group_by(StockBatch.nomenklatura_id, StockBatch.sklad_id)
        .having(func.sum(StockBatch.quantity) != 0)
    )
    result = await session.execute(stmt)
    rows = []
    for nomen_id, sklad_id, qty, cost in result.all():
        nomen = await session.get(Nomenklatura, nomen_id)
        sklad = await session.get(Sklad, sklad_id)
        rows.append(
            {
                "nomenklatura_id": nomen_id,
                "nomenklatura": nomen.name if nomen else f"#{nomen_id}",
                "artikul": nomen.artikul if nomen else None,
                "sklad_id": sklad_id,
                "sklad": sklad.name if sklad else f"#{sklad_id}",
                "quantity": qty,
                "cost": (cost or Decimal("0")).quantize(Decimal("0.01")),
            }
        )
    return rows


async def stock_movements(
    session: AsyncSession, start: date, end: date, nomenklatura_id: int | None = None
) -> list[dict]:
    """Движения товаров за период."""
    stmt = select(StockMovement).where(
        StockMovement.date >= start, StockMovement.date <= end
    )
    if nomenklatura_id:
        stmt = stmt.where(StockMovement.nomenklatura_id == nomenklatura_id)
    stmt = stmt.order_by(StockMovement.date, StockMovement.id)
    result = await session.execute(stmt)
    rows = []
    for m in result.scalars():
        nomen = await session.get(Nomenklatura, m.nomenklatura_id)
        sklad = await session.get(Sklad, m.sklad_id)
        doc = await session.get(Document, m.document_id)
        rows.append(
            {
                "date": m.date,
                "document": doc.number if doc else f"#{m.document_id}",
                "nomenklatura": nomen.name if nomen else f"#{m.nomenklatura_id}",
                "sklad": sklad.name if sklad else f"#{m.sklad_id}",
                "quantity": m.quantity,
                "amount": m.amount,
            }
        )
    return rows


async def sales_report(
    session: AsyncSession, start: date, end: date
) -> list[dict]:
    """Продажи (расходные накладные) за период."""
    stmt = (
        select(Document)
        .where(
            Document.doc_type == DocType.RASHOD.value,
            Document.status == DocumentStatus.POSTED.value,
            Document.date >= start,
            Document.date <= end,
        )
        .order_by(Document.date)
    )
    result = await session.execute(stmt)
    rows = []
    for doc in result.scalars():
        kontragent = await session.get(Kontragent, doc.kontragent_id) if doc.kontragent_id else None
        rows.append(
            {
                "date": doc.date,
                "number": doc.number,
                "kontragent": kontragent.name if kontragent else None,
                "total": doc.total,
            }
        )
    return rows


async def settlement_balances(session: AsyncSession) -> list[dict]:
    """Задолженность контрагентов (положительная — должны нам)."""
    stmt = (
        select(
            SettlementMovement.kontragent_id,
            func.sum(SettlementMovement.amount),
        )
        .group_by(SettlementMovement.kontragent_id)
        .having(func.sum(SettlementMovement.amount) != 0)
    )
    result = await session.execute(stmt)
    rows = []
    for kontragent_id, amount in result.all():
        kontragent = await session.get(Kontragent, kontragent_id)
        rows.append(
            {
                "kontragent_id": kontragent_id,
                "kontragent": kontragent.name if kontragent else f"#{kontragent_id}",
                "debt": amount,
            }
        )
    return rows


async def money_balance(session: AsyncSession) -> Decimal:
    """Суммарный остаток денежных средств."""
    stmt = select(func.coalesce(func.sum(MoneyMovement.amount), 0))
    return (await session.execute(stmt)).scalar() or Decimal("0")


async def money_movements(session: AsyncSession, start: date, end: date) -> list[dict]:
    """Движения денежных средств за период."""
    stmt = (
        select(MoneyMovement)
        .where(MoneyMovement.date >= start, MoneyMovement.date <= end)
        .order_by(MoneyMovement.date, MoneyMovement.id)
    )
    result = await session.execute(stmt)
    rows = []
    for m in result.scalars():
        doc = await session.get(Document, m.document_id)
        kontragent = await session.get(Kontragent, m.kontragent_id) if m.kontragent_id else None
        rows.append(
            {
                "date": m.date,
                "document": doc.number if doc else f"#{m.document_id}",
                "kontragent": kontragent.name if kontragent else None,
                "amount": m.amount,
            }
        )
    return rows
