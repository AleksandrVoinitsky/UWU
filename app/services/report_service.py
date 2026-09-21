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
from app.models.document.base_document import Document, DocumentItem
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


async def settlement_movements(
    session: AsyncSession, start: date, end: date, kontragent_id: int | None = None
) -> list[dict]:
    """Движения по взаиморасчётам за период (детально)."""
    stmt = (
        select(SettlementMovement)
        .where(SettlementMovement.date >= start, SettlementMovement.date <= end)
        .order_by(SettlementMovement.date, SettlementMovement.id)
    )
    if kontragent_id:
        stmt = stmt.where(SettlementMovement.kontragent_id == kontragent_id)
    result = await session.execute(stmt)
    rows = []
    for m in result.scalars():
        doc = await session.get(Document, m.document_id)
        kontragent = await session.get(Kontragent, m.kontragent_id)
        rows.append(
            {
                "date": m.date,
                "document": doc.number if doc else f"#{m.document_id}",
                "kontragent": kontragent.name if kontragent else f"#{m.kontragent_id}",
                "amount": m.amount,
            }
        )
    return rows


async def abc_analysis(session: AsyncSession, start: date, end: date) -> list[dict]:
    """ABC-анализ: группировка ТМЦ по объёму продаж (A/B/C).

    Классы: A — до 80% накопленного объёма, B — следующие 15%, C — остальные.
    """
    stmt = (
        select(
            DocumentItem.nomenklatura_id,
            func.sum(DocumentItem.amount),
        )
        .join(Document, Document.id == DocumentItem.document_id)
        .where(
            Document.doc_type == DocType.RASHOD.value,
            Document.status == DocumentStatus.POSTED.value,
            Document.date >= start,
            Document.date <= end,
        )
        .group_by(DocumentItem.nomenklatura_id)
        .order_by(func.sum(DocumentItem.amount).desc())
    )
    result = await session.execute(stmt)
    data = [(nomen_id, amount) for nomen_id, amount in result.all()]

    total = sum((a for _, a in data), Decimal("0"))
    rows: list[dict] = []
    cumulative = Decimal("0")
    for nomen_id, amount in data:
        nomen = await session.get(Nomenklatura, nomen_id)
        cumulative += amount
        pct = (amount / total * Decimal("100")).quantize(Decimal("0.01")) if total else Decimal("0")
        cum_pct = (cumulative / total * Decimal("100")).quantize(Decimal("0.01")) if total else Decimal("0")
        if cum_pct <= Decimal("80"):
            cls = "A"
        elif cum_pct <= Decimal("95"):
            cls = "B"
        else:
            cls = "C"
        rows.append(
            {
                "nomenklatura": nomen.name if nomen else f"#{nomen_id}",
                "amount": amount,
                "pct": pct,
                "cum_pct": cum_pct,
                "class": cls,
            }
        )
    return rows
