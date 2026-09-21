"""Тесты ценообразования и заявок.

См. также: :mod:`app.services.price_service`, :mod:`app.services.document_service`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.catalog import Nomenklatura, TipTsen
from app.models.enums import DocType
from app.services import catalog_service, document_service, price_service


async def test_auto_price_markup():
    assert price_service.auto_price(Decimal("100"), Decimal("20")) == Decimal("120.00")
    assert price_service.auto_price(Decimal("100"), None) == Decimal("100.00")
    assert price_service.auto_price(None, Decimal("20")) is None


async def test_set_and_clear_explicit_price(seeded_session):
    nomen = await catalog_service.create_one(
        seeded_session, Nomenklatura, code="001", name="Товар", purchase_price=Decimal("100")
    )
    tip = await catalog_service.create_one(
        seeded_session, TipTsen, name="Опт", markup_percent=Decimal("20")
    )

    # Автонаценка: 100 × 1.2 = 120.
    resolved = await price_service.resolve_prices(seeded_session, nomen, [tip])
    assert resolved[tip.id] == Decimal("120.00")

    # Явная цена перекрывает автонаценку.
    await price_service.set_explicit_price(seeded_session, nomen.id, tip.id, Decimal("150"))
    resolved = await price_service.resolve_prices(seeded_session, nomen, [tip])
    assert resolved[tip.id] == Decimal("150.00")

    # Очистка возвращает автонаценку.
    await price_service.clear_explicit_price(seeded_session, nomen.id, tip.id)
    resolved = await price_service.resolve_prices(seeded_session, nomen, [tip])
    assert resolved[tip.id] == Decimal("120.00")


async def test_zakaz_creation(seeded_session):
    from app.models.catalog import Kontragent

    nomen = await catalog_service.create_one(seeded_session, Nomenklatura, code="001", name="Товар")
    kg = await catalog_service.create_one(seeded_session, Kontragent, code="001", name="Клиент")

    zakaz = await document_service.create_document(
        seeded_session,
        doc_type=DocType.ZAKAZ,
        doc_date=date(2025, 1, 10),
        kontragent_id=kg.id,
        extra={"state": "new"},
        items=[{"nomenklatura_id": nomen.id, "quantity": Decimal("2"), "price": Decimal("150")}],
    )
    assert zakaz.doc_type == "zakaz"
    assert zakaz.extra["state"] == "new"
    assert zakaz.total == Decimal("300.00")
