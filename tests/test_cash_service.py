"""Тесты кассовых смен: открытие/закрытие и X/Z-отчёт.

См. также: :mod:`app.services.cash_service`, :mod:`app.models.registry.CashShift`.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.models.catalog import Kassa
from app.models.document.base_document import Document
from app.models.enums import DocType
from app.models.registry import CashShift, MoneyMovement
from app.models.users import User
from app.services import cash_service, catalog_service


async def _make_document(session, number: str, doc_date: date) -> Document:
    doc = Document(doc_type=DocType.PRIHOD, number=number, date=doc_date)
    session.add(doc)
    await session.commit()
    return doc


async def _admin_id(session) -> int:
    return (
        await session.execute(select(User.id).where(User.is_admin.is_(True)))
    ).scalar()


async def _make_kassa(session, name: str) -> Kassa:
    return await catalog_service.create_one(session, Kassa, name=name)


async def _open_shift(session, kassa, opening_amount=Decimal("0")) -> CashShift:
    uid = await _admin_id(session)
    return await cash_service.open_shift(
        session, kassa_id=kassa.id, opening_amount=opening_amount, user_id=uid
    )


async def _add_money(session, doc, *, kassa_id, amount, when) -> None:
    session.add(
        MoneyMovement(document_id=doc.id, date=when, kassa_id=kassa_id, amount=amount)
    )


async def test_open_shift_creates_open_shift(seeded_session):
    kassa = await _make_kassa(seeded_session, "Касса 1")
    uid = await _admin_id(seeded_session)

    shift = await cash_service.open_shift(
        seeded_session,
        kassa_id=kassa.id,
        opening_amount=Decimal("1000.50"),
        user_id=uid,
    )

    assert shift.id is not None
    assert shift.kassa_id == kassa.id
    assert shift.status == "open"
    assert shift.opening_amount == Decimal("1000.50")
    assert shift.opened_by_id == uid
    assert shift.opened_at is not None


async def test_open_shift_returns_existing_shift(seeded_session):
    kassa = await _make_kassa(seeded_session, "Касса 1")

    first = await _open_shift(seeded_session, kassa, Decimal("100"))
    second = await _open_shift(seeded_session, kassa, Decimal("200"))

    # Возвращает уже открытую смену, а не создаёт вторую.
    assert second.id == first.id
    assert second.opening_amount == Decimal("100")

    count = (
        await seeded_session.execute(
            select(func.count(CashShift.id)).where(
                CashShift.kassa_id == kassa.id, CashShift.status == "open"
            )
        )
    ).scalar()
    assert count == 1


async def test_close_shift_sets_closed_status(seeded_session):
    kassa = await _make_kassa(seeded_session, "Касса 1")
    shift = await _open_shift(seeded_session, kassa, Decimal("100"))

    closed = await cash_service.close_shift(seeded_session, shift, Decimal("500.00"))

    assert closed.id == shift.id
    assert closed.status == "closed"
    assert closed.closed_at is not None
    assert closed.closing_amount == Decimal("500.00")


async def test_shift_revenue_sums_positive_movements(seeded_session):
    kassa = await _make_kassa(seeded_session, "Касса 1")
    shift = await _open_shift(seeded_session, kassa)
    shift.opened_at = datetime(2025, 1, 10, tzinfo=timezone.utc)

    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 10))
    await _add_money(seeded_session, doc, kassa_id=kassa.id, amount=Decimal("100.00"), when=date(2025, 1, 10))
    await _add_money(seeded_session, doc, kassa_id=kassa.id, amount=Decimal("50.00"), when=date(2025, 1, 10))
    await _add_money(seeded_session, doc, kassa_id=kassa.id, amount=Decimal("-30.00"), when=date(2025, 1, 10))
    await seeded_session.commit()

    assert await cash_service.shift_revenue(seeded_session, shift) == Decimal("150.00")


async def test_shift_expenses_sums_negative_movements(seeded_session):
    kassa = await _make_kassa(seeded_session, "Касса 1")
    shift = await _open_shift(seeded_session, kassa)
    shift.opened_at = datetime(2025, 1, 10, tzinfo=timezone.utc)

    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 10))
    await _add_money(seeded_session, doc, kassa_id=kassa.id, amount=Decimal("-30.00"), when=date(2025, 1, 10))
    await _add_money(seeded_session, doc, kassa_id=kassa.id, amount=Decimal("-20.00"), when=date(2025, 1, 10))
    await _add_money(seeded_session, doc, kassa_id=kassa.id, amount=Decimal("100.00"), when=date(2025, 1, 10))
    await seeded_session.commit()

    assert await cash_service.shift_expenses(seeded_session, shift) == Decimal("50.00")


async def test_shift_window_excludes_other_kassa(seeded_session):
    kassa_a = await _make_kassa(seeded_session, "Касса A")
    kassa_b = await _make_kassa(seeded_session, "Касса B")
    shift = await _open_shift(seeded_session, kassa_a)
    shift.opened_at = datetime(2025, 1, 10, tzinfo=timezone.utc)

    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 10))
    await _add_money(seeded_session, doc, kassa_id=kassa_a.id, amount=Decimal("100.00"), when=date(2025, 1, 10))
    await _add_money(seeded_session, doc, kassa_id=kassa_b.id, amount=Decimal("200.00"), when=date(2025, 1, 10))
    await seeded_session.commit()

    # Движение по другой кассе не попадает в выручку этой смены.
    assert await cash_service.shift_revenue(seeded_session, shift) == Decimal("100.00")


async def test_shift_window_excludes_outside_dates(seeded_session):
    kassa = await _make_kassa(seeded_session, "Касса 1")
    shift = await _open_shift(seeded_session, kassa)
    shift.opened_at = datetime(2025, 1, 10, tzinfo=timezone.utc)
    await cash_service.close_shift(seeded_session, shift, Decimal("0"))
    shift.closed_at = datetime(2025, 1, 12, tzinfo=timezone.utc)

    doc = await _make_document(seeded_session, "DOC-1", date(2025, 1, 10))
    await _add_money(seeded_session, doc, kassa_id=kassa.id, amount=Decimal("1000.00"), when=date(2025, 1, 9))  # до смены
    await _add_money(seeded_session, doc, kassa_id=kassa.id, amount=Decimal("100.00"), when=date(2025, 1, 11))   # в окне
    await _add_money(seeded_session, doc, kassa_id=kassa.id, amount=Decimal("500.00"), when=date(2025, 1, 13))   # после смены
    await seeded_session.commit()

    # В выручку попадает только движение внутри окна [открытие, закрытие].
    assert await cash_service.shift_revenue(seeded_session, shift) == Decimal("100.00")
