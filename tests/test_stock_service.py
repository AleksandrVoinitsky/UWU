"""Тесты складского учёта: остатки, партии, себестоимость, резервирование.

См. также: :mod:`app.services.stock_service`, :mod:`app.models.registry`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.catalog import Nomenklatura, Sklad
from app.models.document.base_document import Document
from app.models.enums import CostMethod, DocType
from app.models.registry import Reservation, StockBatch, StockMovement
from app.services import catalog_service, stock_service
from app.services.stock_service import InsufficientStockError


async def _make_item(session, code: str, name: str) -> Nomenklatura:
    return await catalog_service.create_one(
        session, Nomenklatura, code=code, name=name, vid="tovar"
    )


async def _make_sklad(session, code: str, name: str) -> Sklad:
    return await catalog_service.create_one(
        session, Sklad, code=code, name=name, tip="optovy"
    )


async def _make_document(session, number: str, doc_date: date) -> Document:
    doc = Document(doc_type=DocType.PRIHOD, number=number, date=doc_date)
    session.add(doc)
    await session.commit()
    return doc


async def _incoming(session, doc, item, sklad, qty, price) -> StockBatch:
    batch = await stock_service.create_incoming(
        session,
        document_id=doc.id,
        date=doc.date,
        nomenklatura_id=item.id,
        sklad_id=sklad.id,
        quantity=qty,
        price=price,
    )
    await session.commit()
    return batch


async def test_create_incoming_creates_batch_and_movement(seeded_session):
    item = await _make_item(seeded_session, "001", "Товар")
    sklad = await _make_sklad(seeded_session, "001", "Склад")
    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 1))

    batch = await _incoming(seeded_session, doc, item, sklad, Decimal("10"), Decimal("100"))

    assert batch.id is not None
    assert batch.nomenklatura_id == item.id
    assert batch.sklad_id == sklad.id
    assert batch.quantity == Decimal("10")
    assert batch.unit_cost == Decimal("100")

    movement = (await seeded_session.execute(select(StockMovement))).scalars().one()
    assert movement.document_id == doc.id
    assert movement.nomenklatura_id == item.id
    assert movement.sklad_id == sklad.id
    assert movement.quantity == Decimal("10")
    assert movement.amount == Decimal("1000")  # 10 * 100
    assert movement.batch_id == batch.id


async def test_get_balance_aggregates_with_and_without_sklad(seeded_session):
    item = await _make_item(seeded_session, "001", "Товар")
    sklad1 = await _make_sklad(seeded_session, "001", "Склад 1")
    sklad2 = await _make_sklad(seeded_session, "002", "Склад 2")
    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 1))

    await _incoming(seeded_session, doc, item, sklad1, Decimal("10"), Decimal("100"))
    await _incoming(seeded_session, doc, item, sklad2, Decimal("5"), Decimal("200"))

    assert await stock_service.get_balance(seeded_session, item.id) == Decimal("15")
    assert await stock_service.get_balance(seeded_session, item.id, sklad1.id) == Decimal("10")
    assert await stock_service.get_balance(seeded_session, item.id, sklad2.id) == Decimal("5")


async def test_get_balances_groups_by_sklad(seeded_session):
    item = await _make_item(seeded_session, "001", "Товар")
    sklad1 = await _make_sklad(seeded_session, "001", "Склад 1")
    sklad2 = await _make_sklad(seeded_session, "002", "Склад 2")
    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 1))

    await _incoming(seeded_session, doc, item, sklad1, Decimal("10"), Decimal("100"))
    await _incoming(seeded_session, doc, item, sklad2, Decimal("5"), Decimal("200"))

    balances = await stock_service.get_balances(seeded_session)
    by_sklad = {sklad_id: qty for (_, sklad_id, qty) in balances}
    assert len(balances) == 2
    assert by_sklad[sklad1.id] == Decimal("10")
    assert by_sklad[sklad2.id] == Decimal("5")

    filtered = await stock_service.get_balances(seeded_session, sklad1.id)
    assert len(filtered) == 1
    assert filtered[0][0] == item.id
    assert filtered[0][1] == sklad1.id
    assert filtered[0][2] == Decimal("10")


async def test_consume_batches_fifo(seeded_session):
    item = await _make_item(seeded_session, "001", "Товар")
    sklad = await _make_sklad(seeded_session, "001", "Склад")
    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 1))

    b1 = await _incoming(seeded_session, doc, item, sklad, Decimal("5"), Decimal("100"))
    b2 = await _incoming(seeded_session, doc, item, sklad, Decimal("5"), Decimal("200"))

    consumed, amount = await stock_service.consume_batches(
        seeded_session,
        nomenklatura_id=item.id,
        sklad_id=sklad.id,
        quantity=Decimal("6"),
        method=CostMethod.FIFO,
    )
    await seeded_session.commit()

    # FIFO: 5 × 100 (старейшая партия) + 1 × 200.
    assert amount == Decimal("700")
    assert len(consumed) == 2
    assert consumed[0].batch_id == b1.id
    assert consumed[0].quantity == Decimal("5")
    assert consumed[0].unit_cost == Decimal("100")
    assert consumed[1].batch_id == b2.id
    assert consumed[1].quantity == Decimal("1")
    assert consumed[1].unit_cost == Decimal("200")

    assert await stock_service.get_balance(seeded_session, item.id, sklad.id) == Decimal("4")


async def test_consume_batches_lifo(seeded_session):
    item = await _make_item(seeded_session, "001", "Товар")
    sklad = await _make_sklad(seeded_session, "001", "Склад")
    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 1))

    b1 = await _incoming(seeded_session, doc, item, sklad, Decimal("5"), Decimal("100"))
    b2 = await _incoming(seeded_session, doc, item, sklad, Decimal("5"), Decimal("200"))

    consumed, amount = await stock_service.consume_batches(
        seeded_session,
        nomenklatura_id=item.id,
        sklad_id=sklad.id,
        quantity=Decimal("6"),
        method=CostMethod.LIFO,
    )
    await seeded_session.commit()

    # LIFO: 5 × 200 (новейшая партия) + 1 × 100.
    assert amount == Decimal("1100")
    assert consumed[0].batch_id == b2.id
    assert consumed[0].quantity == Decimal("5")
    assert consumed[0].unit_cost == Decimal("200")
    assert consumed[1].batch_id == b1.id
    assert consumed[1].quantity == Decimal("1")
    assert consumed[1].unit_cost == Decimal("100")

    assert await stock_service.get_balance(seeded_session, item.id, sklad.id) == Decimal("4")


async def test_consume_batches_average(seeded_session):
    item = await _make_item(seeded_session, "001", "Товар")
    sklad = await _make_sklad(seeded_session, "001", "Склад")
    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 1))

    await _incoming(seeded_session, doc, item, sklad, Decimal("5"), Decimal("100"))
    await _incoming(seeded_session, doc, item, sklad, Decimal("5"), Decimal("200"))

    consumed, amount = await stock_service.consume_batches(
        seeded_session,
        nomenklatura_id=item.id,
        sklad_id=sklad.id,
        quantity=Decimal("4"),
        method=CostMethod.AVERAGE,
    )
    await seeded_session.commit()

    # Средневзвешенная: (5*100 + 5*200) / 10 = 150 → 4 × 150 = 600.
    assert amount == Decimal("600")
    assert len(consumed) == 1
    assert consumed[0].unit_cost == Decimal("150")

    assert await stock_service.get_balance(seeded_session, item.id, sklad.id) == Decimal("6")


async def test_consume_batches_insufficient_stock(seeded_session):
    item = await _make_item(seeded_session, "001", "Товар")
    sklad = await _make_sklad(seeded_session, "001", "Склад")
    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 1))

    await _incoming(seeded_session, doc, item, sklad, Decimal("3"), Decimal("100"))

    with pytest.raises(InsufficientStockError) as exc:
        await stock_service.consume_batches(
            seeded_session,
            nomenklatura_id=item.id,
            sklad_id=sklad.id,
            quantity=Decimal("5"),
            method=CostMethod.FIFO,
        )
    await seeded_session.rollback()  # снимаем FOR UPDATE-блокировку партий
    assert exc.value.available == Decimal("3")
    assert exc.value.required == Decimal("5")


async def test_consume_batches_allow_negative_oversell(seeded_session):
    item = await _make_item(seeded_session, "001", "Товар")
    sklad = await _make_sklad(seeded_session, "001", "Склад")
    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 1))

    await _incoming(seeded_session, doc, item, sklad, Decimal("3"), Decimal("100"))

    consumed, amount = await stock_service.consume_batches(
        seeded_session,
        nomenklatura_id=item.id,
        sklad_id=sklad.id,
        quantity=Decimal("5"),
        method=CostMethod.FIFO,
        allow_negative=True,
    )
    await seeded_session.commit()

    # Списано 3 по 100, нехватка 2 зафиксирована отрицательной партией.
    assert amount == Decimal("300")
    assert len(consumed) == 2
    assert consumed[1].quantity == Decimal("2")

    assert await stock_service.get_balance(seeded_session, item.id, sklad.id) == Decimal("-2")


async def test_reserve_succeeds_when_available(seeded_session):
    item = await _make_item(seeded_session, "001", "Товар")
    sklad = await _make_sklad(seeded_session, "001", "Склад")
    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 1))

    await _incoming(seeded_session, doc, item, sklad, Decimal("5"), Decimal("100"))

    await stock_service.reserve(
        seeded_session, nomenklatura_id=item.id, sklad_id=sklad.id, quantity=Decimal("3")
    )
    await seeded_session.commit()

    reservations = (await seeded_session.execute(select(Reservation))).scalars().all()
    assert len(reservations) == 1
    assert reservations[0].nomenklatura_id == item.id
    assert reservations[0].sklad_id == sklad.id
    assert reservations[0].quantity == Decimal("3")

    assert await stock_service.get_reserved(seeded_session, item.id, sklad.id) == Decimal("3")
    assert await stock_service.get_available(seeded_session, item.id, sklad.id) == Decimal("2")


async def test_reserve_insufficient_stock(seeded_session):
    item = await _make_item(seeded_session, "001", "Товар")
    sklad = await _make_sklad(seeded_session, "001", "Склад")
    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 1))

    await _incoming(seeded_session, doc, item, sklad, Decimal("3"), Decimal("100"))

    with pytest.raises(InsufficientStockError):
        await stock_service.reserve(
            seeded_session, nomenklatura_id=item.id, sklad_id=sklad.id, quantity=Decimal("5")
        )
    await seeded_session.rollback()  # снимаем FOR UPDATE-блокировку партий


async def test_get_available_equals_balance_minus_reserved(seeded_session):
    item = await _make_item(seeded_session, "001", "Товар")
    sklad = await _make_sklad(seeded_session, "001", "Склад")
    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 1))

    await _incoming(seeded_session, doc, item, sklad, Decimal("5"), Decimal("100"))
    await stock_service.reserve(
        seeded_session, nomenklatura_id=item.id, sklad_id=sklad.id, quantity=Decimal("3")
    )
    await seeded_session.commit()

    assert await stock_service.get_balance(seeded_session, item.id, sklad.id) == Decimal("5")
    assert await stock_service.get_available(seeded_session, item.id, sklad.id) == Decimal("2")


async def test_release_for_zakaz_deletes_reservations(seeded_session):
    item = await _make_item(seeded_session, "001", "Товар")
    sklad = await _make_sklad(seeded_session, "001", "Склад")
    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 1))

    await _incoming(seeded_session, doc, item, sklad, Decimal("10"), Decimal("100"))

    zakaz1 = await _make_document(seeded_session, "ZAKAZ-1", date(2025, 1, 1))
    zakaz2 = await _make_document(seeded_session, "ZAKAZ-2", date(2025, 1, 1))

    await stock_service.reserve(
        seeded_session, nomenklatura_id=item.id, sklad_id=sklad.id,
        quantity=Decimal("4"), zakaz_id=zakaz1.id,
    )
    await stock_service.reserve(
        seeded_session, nomenklatura_id=item.id, sklad_id=sklad.id,
        quantity=Decimal("3"), zakaz_id=zakaz2.id,
    )
    await seeded_session.commit()
    assert await stock_service.get_reserved(seeded_session, item.id, sklad.id) == Decimal("7")

    await stock_service.release_for_zakaz(seeded_session, zakaz1.id)
    await seeded_session.commit()

    assert await stock_service.get_reserved(seeded_session, item.id, sklad.id) == Decimal("3")
    reservations = (await seeded_session.execute(select(Reservation))).scalars().all()
    assert len(reservations) == 1
    assert reservations[0].zakaz_id == zakaz2.id
