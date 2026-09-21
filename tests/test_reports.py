"""Тесты отчётов.

См. также: :mod:`app.services.report_service`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.catalog import Kontragent, Nomenklatura, Sklad
from app.models.enums import DocSubtype, DocType
from app.services import catalog_service, document_service, report_service


async def _setup(seeded_session):
    item = await catalog_service.create_one(
        seeded_session, Nomenklatura, code="001", name="Товар", vid="tovar"
    )
    sklad = await catalog_service.create_one(
        seeded_session, Sklad, code="001", name="Склад", tip="optovy"
    )
    kontragent = await catalog_service.create_one(
        seeded_session, Kontragent, code="001", name="Покупатель"
    )
    return item, sklad, kontragent


async def test_stock_balances_report(seeded_session):
    item, sklad, _ = await _setup(seeded_session)
    doc = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PRIHOD,
        doc_date=date(2025, 1, 1),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("7"), "price": Decimal("50")}],
    )
    await document_service.post_document(seeded_session, doc)

    balances = await report_service.stock_balances(seeded_session)
    assert len(balances) == 1
    assert balances[0]["quantity"] == Decimal("7.000")
    assert balances[0]["nomenklatura"] == "Товар"


async def test_settlement_report(seeded_session):
    item, sklad, kontragent = await _setup(seeded_session)
    doc = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PRIHOD,
        doc_date=date(2025, 1, 1),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("10"), "price": Decimal("100")}],
    )
    await document_service.post_document(seeded_session, doc)

    rashod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.RASHOD,
        subtype=DocSubtype.CREDIT,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad.id,
        kontragent_id=kontragent.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("3"), "price": Decimal("120")}],
    )
    await document_service.post_document(seeded_session, rashod)

    rows = await report_service.settlement_balances(seeded_session)
    assert len(rows) == 1
    assert rows[0]["debt"] == Decimal("360.00")


async def test_money_balance(seeded_session):
    _, _, kontragent = await _setup(seeded_session)
    pko = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PRIHODNY_KASSOVY_ORDER,
        doc_date=date(2025, 1, 1),
        kontragent_id=kontragent.id,
        total=Decimal("500"),
    )
    await document_service.post_document(seeded_session, pko)

    balance = await report_service.money_balance(seeded_session)
    assert balance == Decimal("500.00")
