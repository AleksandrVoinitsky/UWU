"""Отчёты: остатки, движения, продажи, взаиморасчёты, деньги.

Все отчёты строятся агрегацией регистров. Возвращают списки словарей, готовых к
сериализации в JSON или отображению в шаблонах.

См. также: :mod:`app.models.registry`, :mod:`app.api.reports`.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Kontragent, Nomenklatura, Sklad
from app.models.document.base_document import Document, DocumentItem
from app.models.enums import DocType, DocumentStatus
from app.models.registry import (
    AccountingEntry,
    MoneyMovement,
    Reservation,
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
            StockBatch.ownership,
            func.sum(StockBatch.quantity),
            func.sum(StockBatch.quantity * StockBatch.unit_cost),
        )
        .group_by(StockBatch.nomenklatura_id, StockBatch.sklad_id, StockBatch.ownership)
        .having(func.sum(StockBatch.quantity) != 0)
    )
    result = await session.execute(stmt)
    # Резерв по позициям.
    res_stmt = select(
        Reservation.nomenklatura_id,
        Reservation.sklad_id,
        func.sum(Reservation.quantity),
    ).group_by(Reservation.nomenklatura_id, Reservation.sklad_id)
    res_result = await session.execute(res_stmt)
    reserved_map = {(r[0], r[1]): r[2] for r in res_result.all()}

    rows = []
    for nomen_id, sklad_id, ownership, qty, cost in result.all():
        nomen = await session.get(Nomenklatura, nomen_id)
        sklad = await session.get(Sklad, sklad_id)
        reserved = reserved_map.get((nomen_id, sklad_id), Decimal("0"))
        rows.append(
            {
                "nomenklatura_id": nomen_id,
                "nomenklatura": nomen.name if nomen else f"#{nomen_id}",
                "artikul": nomen.artikul if nomen else None,
                "sklad_id": sklad_id,
                "sklad": sklad.name if sklad else f"#{sklad_id}",
                "ownership": ownership,
                "quantity": qty,
                "reserved": reserved,
                "available": qty - reserved,
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
        # Себестоимость = сумма расходных движений по документу.
        cost_stmt = select(func.coalesce(func.sum(StockMovement.amount), 0)).where(
            StockMovement.document_id == doc.id, StockMovement.quantity < 0
        )
        cost = -(await session.execute(cost_stmt)).scalar() or Decimal("0")
        rows.append(
            {
                "date": doc.date,
                "number": doc.number,
                "kontragent": kontragent.name if kontragent else None,
                "total": doc.total,
                "cost": cost,
                "profit": doc.total - cost,
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


async def accounting_entries(session: AsyncSession, start: date, end: date) -> list[dict]:
    """Журнал бухгалтерских проводок за период."""
    stmt = (
        select(AccountingEntry)
        .where(AccountingEntry.date >= start, AccountingEntry.date <= end)
        .order_by(AccountingEntry.date, AccountingEntry.id)
    )
    result = await session.execute(stmt)
    rows = []
    for e in result.scalars():
        doc = await session.get(Document, e.document_id)
        kontragent = await session.get(Kontragent, e.kontragent_id) if e.kontragent_id else None
        rows.append(
            {
                "date": e.date,
                "document": doc.number if doc else f"#{e.document_id}",
                "debit": e.account_debit,
                "credit": e.account_credit,
                "amount": e.amount,
                "kontragent": kontragent.name if kontragent else None,
            }
        )
    return rows


async def commission_report(session: AsyncSession) -> dict:
    """Отчёт по комиссионной торговле: принятые на реализацию + долг комитентам."""
    stmt = (
        select(
            StockBatch.nomenklatura_id,
            StockBatch.sklad_id,
            func.sum(StockBatch.quantity),
        )
        .where(StockBatch.ownership == "received", StockBatch.quantity > 0)
        .group_by(StockBatch.nomenklatura_id, StockBatch.sklad_id)
    )
    result = await session.execute(stmt)
    received = []
    for nomen_id, sklad_id, qty in result.all():
        nomen = await session.get(Nomenklatura, nomen_id)
        sklad = await session.get(Sklad, sklad_id)
        received.append(
            {
                "nomenklatura": nomen.name if nomen else f"#{nomen_id}",
                "sklad": sklad.name if sklad else f"#{sklad_id}",
                "quantity": qty,
            }
        )

    # Долг комитентам (отрицательные суммы взаиморасчётов).
    debt_stmt = select(func.coalesce(func.sum(SettlementMovement.amount), 0)).where(
        SettlementMovement.amount < 0
    )
    debt = -(await session.execute(debt_stmt)).scalar() or Decimal("0")

    return {"received": received, "debt": debt}


async def open_invoices(
    session: AsyncSession, kontragent_id: int | None = None
) -> list[dict]:
    """Задолженность по документам: накладные с ненулевым остатком взаиморасчётов.

    Положительный остаток — контрагент должен нам, отрицательный — мы должны.
    """
    stmt = (
        select(
            SettlementMovement.base_document_id,
            func.sum(SettlementMovement.amount),
        )
        .where(SettlementMovement.base_document_id.isnot(None))
        .group_by(SettlementMovement.base_document_id)
        .having(func.sum(SettlementMovement.amount) != 0)
    )
    result = await session.execute(stmt)
    rows = []
    for base_id, open_amount in result.all():
        doc = await session.get(Document, base_id)
        if doc is None:
            continue
        if kontragent_id and doc.kontragent_id != kontragent_id:
            continue
        kontragent = await session.get(Kontragent, doc.kontragent_id) if doc.kontragent_id else None
        rows.append(
            {
                "document_id": base_id,
                "number": doc.number,
                "date": doc.date,
                "doc_type": doc.doc_type,
                "kontragent": kontragent.name if kontragent else "—",
                "total": doc.total,
                "open": open_amount,
            }
        )
    rows.sort(key=lambda r: r["date"])
    return rows


async def batch_report(session: AsyncSession) -> list[dict]:
    """Отчёт по партиям: остатки партий с себестоимостью."""
    stmt = (
        select(StockBatch)
        .where(StockBatch.quantity > 0)
        .order_by(StockBatch.nomenklatura_id, StockBatch.created_at)
    )
    result = await session.execute(stmt)
    rows = []
    for b in result.scalars():
        nomen = await session.get(Nomenklatura, b.nomenklatura_id)
        sklad = await session.get(Sklad, b.sklad_id)
        rows.append(
            {
                "nomenklatura": nomen.name if nomen else f"#{b.nomenklatura_id}",
                "sklad": sklad.name if sklad else f"#{b.sklad_id}",
                "quantity": b.quantity,
                "unit_cost": b.unit_cost,
                "cost": (b.quantity * b.unit_cost).quantize(Decimal("0.01")),
                "ownership": b.ownership,
                "created_at": b.created_at.date() if b.created_at else None,
            }
        )
    return rows


async def cash_book(session: AsyncSession, start: date, end: date) -> list[dict]:
    """Кассовая книга: движения денег по дням (приход/расход/остаток)."""
    stmt = (
        select(
            MoneyMovement.date,
            func.coalesce(func.sum(case((MoneyMovement.amount > 0, MoneyMovement.amount), else_=0)), 0),
            func.coalesce(func.sum(case((MoneyMovement.amount < 0, MoneyMovement.amount), else_=0)), 0),
        )
        .where(MoneyMovement.date >= start, MoneyMovement.date <= end)
        .group_by(MoneyMovement.date)
        .order_by(MoneyMovement.date)
    )
    result = await session.execute(stmt)
    rows = []
    running = Decimal("0")
    for day, income, expense in result.all():
        running += income + expense
        rows.append(
            {
                "date": day,
                "income": income,
                "expense": expense,
                "balance": running,
            }
        )
    return rows


async def turnover_statement(
    session: AsyncSession, start: date, end: date
) -> list[dict]:
    """Оборотная ведомость: начальный остаток, приход, расход, конечный остаток."""
    stmt = (
        select(
            StockMovement.nomenklatura_id,
            StockMovement.sklad_id,
            func.coalesce(
                func.sum(case((StockMovement.date < start, StockMovement.quantity), else_=0)), 0
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                StockMovement.date >= start,
                                StockMovement.date <= end,
                                StockMovement.quantity > 0,
                            ),
                            StockMovement.quantity,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                StockMovement.date >= start,
                                StockMovement.date <= end,
                                StockMovement.quantity < 0,
                            ),
                            StockMovement.quantity,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .group_by(StockMovement.nomenklatura_id, StockMovement.sklad_id)
    )
    result = await session.execute(stmt)
    rows = []
    for nomen_id, sklad_id, opening, incoming, outgoing in result.all():
        if opening == 0 and incoming == 0 and outgoing == 0:
            continue
        nomen = await session.get(Nomenklatura, nomen_id)
        sklad = await session.get(Sklad, sklad_id)
        rows.append(
            {
                "nomenklatura": nomen.name if nomen else f"#{nomen_id}",
                "sklad": sklad.name if sklad else f"#{sklad_id}",
                "opening": opening,
                "incoming": incoming,
                "outgoing": outgoing,
                "closing": opening + incoming + outgoing,
            }
        )
    rows.sort(key=lambda r: r["nomenklatura"])
    return rows


async def item_card(
    session: AsyncSession, nomenklatura_id: int, start: date | None = None, end: date | None = None
) -> list[dict]:
    """Карточка товара: движения по документам."""
    stmt = select(StockMovement).where(StockMovement.nomenklatura_id == nomenklatura_id)
    if start:
        stmt = stmt.where(StockMovement.date >= start)
    if end:
        stmt = stmt.where(StockMovement.date <= end)
    stmt = stmt.order_by(StockMovement.date, StockMovement.id)
    result = await session.execute(stmt)
    rows = []
    for m in result.scalars():
        doc = await session.get(Document, m.document_id)
        sklad = await session.get(Sklad, m.sklad_id)
        rows.append(
            {
                "date": m.date,
                "document": doc.number if doc else f"#{m.document_id}",
                "doc_type": doc.doc_type if doc else "",
                "sklad": sklad.name if sklad else f"#{m.sklad_id}",
                "quantity": m.quantity,
                "amount": m.amount,
            }
        )
    return rows


async def purchase_sales_book(
    session: AsyncSession, start: date, end: date
) -> list[dict]:
    """Книга покупок/продаж: приходные и расходные накладные с НДС за период."""
    stmt = (
        select(Document)
        .where(
            Document.doc_type.in_([DocType.PRIHOD.value, DocType.RASHOD.value]),
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
                "doc_type": doc.doc_type,
                "kind": "Продажа" if doc.doc_type == DocType.RASHOD.value else "Покупка",
                "kontragent": kontragent.name if kontragent else "—",
                "total": doc.total,
                "nds": doc.nds_total,
            }
        )
    return rows


# --- Сводные показатели для дашборда ---


async def sales_summary(session: AsyncSession, start: date, end: date) -> dict:
    """Сводные показатели продаж за период.

    Возвращает выручку, прибыль, себестоимость, количество продаж, средний чек и
    сумму закупок по проведённым накладным за период.
    """
    revenue = (
        (await session.execute(
            select(func.coalesce(func.sum(Document.total), 0)).where(
                Document.doc_type == DocType.RASHOD.value,
                Document.status == DocumentStatus.POSTED.value,
                Document.date >= start,
                Document.date <= end,
            )
        )).scalar()
        or Decimal("0")
    )

    orders_count = (
        (await session.execute(
            select(func.count(Document.id)).where(
                Document.doc_type == DocType.RASHOD.value,
                Document.status == DocumentStatus.POSTED.value,
                Document.date >= start,
                Document.date <= end,
            )
        )).scalar()
        or 0
    )

    # Себестоимость = сумма расходных движений по проведённым расходным накладным.
    cost = -(
        (await session.execute(
            select(func.coalesce(func.sum(StockMovement.amount), 0))
            .join(Document, Document.id == StockMovement.document_id)
            .where(
                Document.doc_type == DocType.RASHOD.value,
                Document.status == DocumentStatus.POSTED.value,
                Document.date >= start,
                Document.date <= end,
                StockMovement.quantity < 0,
            )
        )).scalar()
        or Decimal("0")
    )

    purchases = (
        (await session.execute(
            select(func.coalesce(func.sum(Document.total), 0)).where(
                Document.doc_type == DocType.PRIHOD.value,
                Document.status == DocumentStatus.POSTED.value,
                Document.date >= start,
                Document.date <= end,
            )
        )).scalar()
        or Decimal("0")
    )

    profit = revenue - cost
    avg_check = (
        (revenue / orders_count).quantize(Decimal("0.01")) if orders_count else Decimal("0")
    )
    return {
        "revenue": revenue,
        "profit": profit,
        "cost": cost,
        "orders_count": orders_count,
        "avg_check": avg_check,
        "purchases": purchases,
    }


async def daily_sales(session: AsyncSession, start: date, end: date) -> list[dict]:
    """Выручка, прибыль и количество продаж по дням за период.

    Дни без продаж заполняются нулями (для непрерывного графика).
    """
    revenue_by_day: dict[date, Decimal] = {}
    orders_by_day: dict[date, int] = {}
    for d, total, cnt in (
        await session.execute(
            select(Document.date, func.sum(Document.total), func.count(Document.id))
            .where(
                Document.doc_type == DocType.RASHOD.value,
                Document.status == DocumentStatus.POSTED.value,
                Document.date >= start,
                Document.date <= end,
            )
            .group_by(Document.date)
        )
    ).all():
        revenue_by_day[d] = total
        orders_by_day[d] = cnt

    cost_by_day = {
        d: -(amount or Decimal("0"))
        for d, amount in (
            await session.execute(
                select(StockMovement.date, func.sum(StockMovement.amount))
                .join(Document, Document.id == StockMovement.document_id)
                .where(
                    Document.doc_type == DocType.RASHOD.value,
                    Document.status == DocumentStatus.POSTED.value,
                    StockMovement.quantity < 0,
                    StockMovement.date >= start,
                    StockMovement.date <= end,
                )
                .group_by(StockMovement.date)
            )
        ).all()
    }

    rows: list[dict] = []
    current = start
    while current <= end:
        revenue = revenue_by_day.get(current, Decimal("0"))
        rows.append(
            {
                "date": current.isoformat(),
                "revenue": revenue,
                "profit": revenue - cost_by_day.get(current, Decimal("0")),
                "orders": orders_by_day.get(current, 0),
            }
        )
        current += timedelta(days=1)
    return rows


async def daily_money_flow(
    session: AsyncSession, start: date, end: date
) -> list[dict]:
    """Приход и расход денежных средств по дням за период (нули в пустые дни)."""
    income_by_day: dict[date, Decimal] = {}
    expense_by_day: dict[date, Decimal] = {}
    for d, income, expense in (
        await session.execute(
            select(
                MoneyMovement.date,
                func.coalesce(
                    func.sum(case((MoneyMovement.amount > 0, MoneyMovement.amount), else_=0)), 0
                ),
                func.coalesce(
                    func.sum(case((MoneyMovement.amount < 0, MoneyMovement.amount), else_=0)), 0
                ),
            )
            .where(MoneyMovement.date >= start, MoneyMovement.date <= end)
            .group_by(MoneyMovement.date)
        )
    ).all():
        income_by_day[d] = income
        expense_by_day[d] = expense

    rows: list[dict] = []
    current = start
    while current <= end:
        rows.append(
            {
                "date": current.isoformat(),
                "income": income_by_day.get(current, Decimal("0")),
                "expense": expense_by_day.get(current, Decimal("0")),
            }
        )
        current += timedelta(days=1)
    return rows


async def top_items(
    session: AsyncSession, start: date, end: date, limit: int = 10
) -> list[dict]:
    """Топ товаров по выручке за период."""
    result = await session.execute(
        select(
            Nomenklatura.name,
            func.sum(DocumentItem.quantity),
            func.sum(DocumentItem.amount),
        )
        .join(Document, Document.id == DocumentItem.document_id)
        .join(Nomenklatura, Nomenklatura.id == DocumentItem.nomenklatura_id)
        .where(
            Document.doc_type == DocType.RASHOD.value,
            Document.status == DocumentStatus.POSTED.value,
            Document.date >= start,
            Document.date <= end,
        )
        .group_by(Nomenklatura.name)
        .order_by(func.sum(DocumentItem.amount).desc())
        .limit(limit)
    )
    return [
        {"name": name, "quantity": qty, "amount": amount}
        for name, qty, amount in result.all()
    ]


async def top_counterparties(
    session: AsyncSession, start: date, end: date, limit: int = 10
) -> list[dict]:
    """Топ клиентов по выручке за период."""
    result = await session.execute(
        select(Kontragent.name, func.sum(Document.total))
        .join(Document, Document.kontragent_id == Kontragent.id)
        .where(
            Document.doc_type == DocType.RASHOD.value,
            Document.status == DocumentStatus.POSTED.value,
            Document.date >= start,
            Document.date <= end,
        )
        .group_by(Kontragent.name)
        .order_by(func.sum(Document.total).desc())
        .limit(limit)
    )
    return [{"name": name, "amount": amount} for name, amount in result.all()]


async def low_stock(
    session: AsyncSession, threshold: int = 5, limit: int = 10
) -> list[dict]:
    """Товары с низким/нулевым остатком (суммарно по всем складам)."""
    result = await session.execute(
        select(
            Nomenklatura.name,
            func.coalesce(func.sum(StockBatch.quantity), 0),
        )
        .outerjoin(StockBatch, StockBatch.nomenklatura_id == Nomenklatura.id)
        .group_by(Nomenklatura.id, Nomenklatura.name)
        .having(func.coalesce(func.sum(StockBatch.quantity), 0) <= threshold)
        .order_by(func.coalesce(func.sum(StockBatch.quantity), 0))
        .limit(limit)
    )
    return [{"name": name, "quantity": qty} for name, qty in result.all()]


async def recent_sales(session: AsyncSession, limit: int = 10) -> list[dict]:
    """Последние проведённые расходные накладные (продажи)."""
    result = await session.execute(
        select(Document)
        .where(
            Document.doc_type == DocType.RASHOD.value,
            Document.status == DocumentStatus.POSTED.value,
        )
        .order_by(Document.date.desc(), Document.id.desc())
        .limit(limit)
    )
    rows = []
    for doc in result.scalars():
        kontragent = await session.get(Kontragent, doc.kontragent_id) if doc.kontragent_id else None
        cost = -(
            (await session.execute(
                select(func.coalesce(func.sum(StockMovement.amount), 0)).where(
                    StockMovement.document_id == doc.id, StockMovement.quantity < 0
                )
            )).scalar()
            or Decimal("0")
        )
        rows.append(
            {
                "date": doc.date,
                "number": doc.number,
                "kontragent": kontragent.name if kontragent else None,
                "total": doc.total,
                "profit": doc.total - cost,
            }
        )
    return rows


async def replenishment_recommendations(
    session: AsyncSession,
    *,
    lookback_days: int = 30,
    lead_days: int = 7,
    safety_days: int = 3,
) -> list[dict]:
    """Рекомендации к заказу у поставщика (по всей номенклатуре).

    Для каждой позиции рассчитывает средние продажи за ``lookback_days`` дней и
    оптимальный остаток (спрос за время поставки + страховой запас), затем —
    рекомендуемое количество к заказу ``to_order = target - stock``.

    Возвращает список, отсортированный по убыванию количества к заказу
    (позиции, требующие закупки, — сверху). Позиции без продаж помечаются
    ``status="no_sales"``.
    """
    today = date.today()
    start = today - timedelta(days=lookback_days)

    stock_rows = (
        await session.execute(
            select(
                Nomenklatura.id,
                Nomenklatura.name,
                func.coalesce(func.sum(StockBatch.quantity), 0),
            )
            .outerjoin(StockBatch, StockBatch.nomenklatura_id == Nomenklatura.id)
            .group_by(Nomenklatura.id, Nomenklatura.name)
        )
    ).all()

    sold_map = {
        nid: qty
        for nid, qty in (
            await session.execute(
                select(DocumentItem.nomenklatura_id, func.sum(DocumentItem.quantity))
                .join(Document, Document.id == DocumentItem.document_id)
                .where(
                    Document.doc_type == DocType.RASHOD.value,
                    Document.status == DocumentStatus.POSTED.value,
                    Document.date >= start,
                )
                .group_by(DocumentItem.nomenklatura_id)
            )
        ).all()
    }

    rows: list[dict] = []
    for nid, name, stock in stock_rows:
        stock_qty = stock or Decimal("0")
        sold = sold_map.get(nid, Decimal("0")) or Decimal("0")

        if sold > 0:
            avg_daily = sold / Decimal(lookback_days)
            reorder_point = (avg_daily * lead_days).to_integral_value(
                rounding=ROUND_CEILING
            )
            target = (avg_daily * (lead_days + safety_days)).to_integral_value(
                rounding=ROUND_CEILING
            )
        else:
            avg_daily = Decimal("0")
            reorder_point = Decimal("0")
            target = Decimal("0")

        to_order = max(Decimal("0"), target - stock_qty)
        if sold == 0:
            status = "no_sales"
        elif stock_qty <= reorder_point:
            status = "order"
        else:
            status = "ok"

        rows.append(
            {
                "nomenklatura": name,
                "stock": stock_qty,
                "sold": sold,
                "avg_daily": avg_daily,
                "reorder_point": reorder_point,
                "target": target,
                "to_order": to_order,
                "status": status,
            }
        )

    rows.sort(key=lambda r: (-float(r["to_order"]), r["nomenklatura"]))
    return rows
