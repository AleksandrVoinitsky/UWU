"""Регрессионные тесты на отложенные исправления аудита (M4/M12/M13).

Покрывает: переоценку товаров (M12), полные бухгалтерские проводки (M13),
изоляцию по фирме (M4).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models.catalog import Firma, Kassa, Kontragent, Nomenklatura, Sklad
from app.models.enums import DocSubtype, DocType
from app.models.registry import AccountingEntry, MoneyMovement, StockBatch
from app.services import (
    catalog_service,
    document_service,
    report_service,
)


async def _item(seeded_session, code="001", name="Товар") -> Nomenklatura:
    return await catalog_service.create_one(
        seeded_session, Nomenklatura, code=code, name=name, vid="tovar"
    )


async def _sklad(seeded_session, code="001", name="Склад") -> Sklad:
    return await catalog_service.create_one(
        seeded_session, Sklad, code=code, name=name, tip="optovy"
    )


async def _prihod(seeded_session, item, sklad, qty, price) -> document_service.Document:
    doc = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PRIHOD,
        doc_date=date(2025, 1, 1),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": qty, "price": price}],
    )
    return await document_service.post_document(seeded_session, doc)


# --- M12: переоценка товаров ---


async def test_pereocenka_revalues_batches_and_generates_entry(seeded_session):
    item = await _item(seeded_session)
    sklad = await _sklad(seeded_session)
    await _prihod(seeded_session, item, sklad, Decimal("5"), Decimal("100"))

    pere = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PEREOCENKA,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("0"), "price": Decimal("150")}],
    )
    await document_service.post_document(seeded_session, pere)

    batch = (
        await seeded_session.execute(
            select(StockBatch).where(StockBatch.nomenklatura_id == item.id)
        )
    ).scalar_one()
    assert batch.unit_cost == Decimal("150")

    entry = (
        await seeded_session.execute(
            select(AccountingEntry).where(AccountingEntry.document_id == pere.id)
        )
    ).scalars().all()
    assert len(entry) == 1
    assert entry[0].account_debit == "41"
    assert entry[0].account_credit == "91.1"
    assert entry[0].amount == Decimal("250.00")  # (150 - 100) × 5


async def test_pereocenka_unpost_restores_cost(seeded_session):
    item = await _item(seeded_session)
    sklad = await _sklad(seeded_session)
    await _prihod(seeded_session, item, sklad, Decimal("5"), Decimal("100"))

    pere = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PEREOCENKA,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("0"), "price": Decimal("150")}],
    )
    await document_service.post_document(seeded_session, pere)
    await document_service.unpost_document(seeded_session, pere)

    batch = (
        await seeded_session.execute(
            select(StockBatch).where(StockBatch.nomenklatura_id == item.id)
        )
    ).scalar_one()
    assert batch.unit_cost == Decimal("100")


# --- M13: полные проводки ---


async def test_spisanie_generates_expense_entry(seeded_session):
    item = await _item(seeded_session)
    sklad = await _sklad(seeded_session)
    await _prihod(seeded_session, item, sklad, Decimal("10"), Decimal("100"))

    spis = await document_service.create_document(
        seeded_session,
        doc_type=DocType.SPISANIE,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("3"), "price": Decimal("0")}],
    )
    await document_service.post_document(seeded_session, spis)

    entry = (
        await seeded_session.execute(
            select(AccountingEntry).where(AccountingEntry.document_id == spis.id)
        )
    ).scalars().all()
    assert any(e.account_debit == "91.2" and e.account_credit == "41" and e.amount == Decimal("300.00") for e in entry)


async def test_oprihodovanie_generates_income_entry(seeded_session):
    item = await _item(seeded_session)
    sklad = await _sklad(seeded_session)

    opr = await document_service.create_document(
        seeded_session,
        doc_type=DocType.OPRIHODOVANIE,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("4"), "price": Decimal("50")}],
    )
    await document_service.post_document(seeded_session, opr)

    entry = (
        await seeded_session.execute(
            select(AccountingEntry).where(AccountingEntry.document_id == opr.id)
        )
    ).scalars().all()
    assert any(e.account_debit == "41" and e.account_credit == "91.1" and e.amount == Decimal("200.00") for e in entry)


# --- M4: изоляция по фирме ---


async def test_money_movement_records_firma_and_filters(seeded_session):
    firma = await catalog_service.create_one(seeded_session, Firma, name="ООО Ромашка")
    item = await _item(seeded_session)
    sklad = await _sklad(seeded_session)
    kontragent = await catalog_service.create_one(
        seeded_session, Kontragent, code="001", name="Покупатель"
    )
    kassa = await catalog_service.create_one(seeded_session, Kassa, name="Касса")
    await _prihod(seeded_session, item, sklad, Decimal("10"), Decimal("100"))

    rashod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.RASHOD,
        subtype=DocSubtype.CASH,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad.id,
        kontragent_id=kontragent.id,
        kassa_id=kassa.id,
        firma_id=firma.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("2"), "price": Decimal("150")}],
    )
    await document_service.post_document(seeded_session, rashod)

    money = (
        await seeded_session.execute(
            select(MoneyMovement).where(MoneyMovement.document_id == rashod.id)
        )
    ).scalar_one()
    assert money.firma_id == firma.id

    assert await report_service.money_balance(seeded_session, firma_id=firma.id) == Decimal("300.00")
    assert await report_service.money_balance(seeded_session, firma_id=999999) == Decimal("0")
