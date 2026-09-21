"""Тесты документов: проведение, контроль остатков, себестоимость.

См. также: :mod:`app.services.document_service`,
:mod:`app.services.stock_service`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.catalog import Nomenklatura, Sklad
from app.models.enums import DocSubtype, DocType
from app.services import catalog_service, document_service
from app.services.stock_service import InsufficientStockError, get_balance


async def _make_item(seeded_session) -> Nomenklatura:
    return await catalog_service.create_one(
        seeded_session, Nomenklatura, code="001", name="Товар", vid="tovar"
    )


async def _make_sklad(seeded_session) -> Sklad:
    return await catalog_service.create_one(
        seeded_session, Sklad, code="001", name="Склад", tip="optovy"
    )


async def _prihod(seeded_session, item, sklad, qty, price) -> document_service.Document:
    return await document_service.create_document(
        seeded_session,
        doc_type=DocType.PRIHOD,
        doc_date=date(2025, 1, 1),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": qty, "price": price}],
    )


async def test_prihod_posts_and_updates_balance(seeded_session):
    item = await _make_item(seeded_session)
    sklad = await _make_sklad(seeded_session)

    doc = await _prihod(seeded_session, item, sklad, Decimal("10"), Decimal("100"))
    await document_service.post_document(seeded_session, doc)

    balance = await get_balance(seeded_session, item.id, sklad.id)
    assert balance == Decimal("10")


async def test_rashod_consumes_fifo(seeded_session):
    item = await _make_item(seeded_session)
    sklad = await _make_sklad(seeded_session)

    # Два прихода по разным ценам.
    d1 = await _prihod(seeded_session, item, sklad, Decimal("5"), Decimal("100"))
    await document_service.post_document(seeded_session, d1)
    d2 = await _prihod(seeded_session, item, sklad, Decimal("5"), Decimal("200"))
    await document_service.post_document(seeded_session, d2)

    # Расход 5 единиц — по FIFO себестоимость 5 * 100 = 500.
    rashod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.RASHOD,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("5"), "price": Decimal("300")}],
    )
    await document_service.post_document(seeded_session, rashod)

    balance = await get_balance(seeded_session, item.id, sklad.id)
    assert balance == Decimal("5")

    # Проверяем, что осталась партия с ценой 200 (FIFO списал партию 100).
    from app.models.registry import StockBatch
    from sqlalchemy import select

    batches = (
        await seeded_session.execute(
            select(StockBatch).where(
                StockBatch.nomenklatura_id == item.id, StockBatch.quantity > 0
            )
        )
    ).scalars().all()
    assert len(batches) == 1
    assert batches[0].unit_cost == Decimal("200")


async def test_rashod_insufficient_stock(seeded_session):
    item = await _make_item(seeded_session)
    sklad = await _make_sklad(seeded_session)

    d1 = await _prihod(seeded_session, item, sklad, Decimal("3"), Decimal("100"))
    await document_service.post_document(seeded_session, d1)

    rashod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.RASHOD,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("5"), "price": Decimal("300")}],
    )
    with pytest.raises(InsufficientStockError):
        await document_service.post_document(seeded_session, rashod)


async def test_peremeshenie_moves_stock(seeded_session):
    item = await _make_item(seeded_session)
    sklad_from = await _make_sklad(seeded_session)
    sklad_to = await catalog_service.create_one(
        seeded_session, Sklad, code="002", name="Склад 2", tip="optovy"
    )

    d1 = await _prihod(seeded_session, item, sklad_from, Decimal("10"), Decimal("100"))
    await document_service.post_document(seeded_session, d1)

    move = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PEREMESHENIE,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad_from.id,
        sklad_to_id=sklad_to.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("4"), "price": Decimal("100")}],
    )
    await document_service.post_document(seeded_session, move)

    assert await get_balance(seeded_session, item.id, sklad_from.id) == Decimal("6")
    assert await get_balance(seeded_session, item.id, sklad_to.id) == Decimal("4")


async def test_unpost_restores_stock(seeded_session):
    item = await _make_item(seeded_session)
    sklad = await _make_sklad(seeded_session)

    d1 = await _prihod(seeded_session, item, sklad, Decimal("10"), Decimal("100"))
    await document_service.post_document(seeded_session, d1)
    assert await get_balance(seeded_session, item.id, sklad.id) == Decimal("10")

    await document_service.unpost_document(seeded_session, d1)
    assert await get_balance(seeded_session, item.id, sklad.id) == Decimal("0")


async def test_settlement_after_credit_sale(seeded_session):
    from app.models.catalog import Kontragent
    from app.models.registry import SettlementMovement
    from sqlalchemy import func, select

    item = await _make_item(seeded_session)
    sklad = await _make_sklad(seeded_session)
    kontragent = await catalog_service.create_one(
        seeded_session, Kontragent, code="001", name="Покупатель"
    )

    d1 = await _prihod(seeded_session, item, sklad, Decimal("10"), Decimal("100"))
    await document_service.post_document(seeded_session, d1)

    rashod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.RASHOD,
        subtype=DocSubtype.CREDIT,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad.id,
        kontragent_id=kontragent.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("2"), "price": Decimal("150")}],
    )
    await document_service.post_document(seeded_session, rashod)

    debt = (
        await seeded_session.execute(
            select(func.sum(SettlementMovement.amount)).where(
                SettlementMovement.kontragent_id == kontragent.id
            )
        )
    ).scalar()
    assert debt == Decimal("300.00")


async def test_inventory_adjusts_stock(seeded_session):
    item = await _make_item(seeded_session)
    sklad = await _make_sklad(seeded_session)

    d1 = await _prihod(seeded_session, item, sklad, Decimal("5"), Decimal("100"))
    await document_service.post_document(seeded_session, d1)
    assert await get_balance(seeded_session, item.id, sklad.id) == Decimal("5")

    # Инвентаризация: фактически 2 (недостача 3).
    inv = await document_service.create_document(
        seeded_session,
        doc_type=DocType.INVENTARIZACIYA,
        doc_date=date(2025, 1, 5),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "sklad_id": sklad.id, "quantity": Decimal("2"), "price": Decimal("0")}],
    )
    await document_service.post_document(seeded_session, inv)

    assert await get_balance(seeded_session, item.id, sklad.id) == Decimal("2")


async def test_reservation_reduces_available(seeded_session):
    from app.services import stock_service

    item = await _make_item(seeded_session)
    sklad = await _make_sklad(seeded_session)

    d1 = await _prihod(seeded_session, item, sklad, Decimal("5"), Decimal("100"))
    await document_service.post_document(seeded_session, d1)

    # Резервируем 3 из 5.
    await stock_service.reserve(
        seeded_session, nomenklatura_id=item.id, sklad_id=sklad.id,
        quantity=Decimal("3"), zakaz_id=None,
    )
    await seeded_session.commit()

    assert await stock_service.get_available(seeded_session, item.id, sklad.id) == Decimal("2")
    assert await stock_service.get_reserved(seeded_session, item.id, sklad.id) == Decimal("3")
