"""Тесты продажи заявки покупателя через РМК.

Проверяют, что продажа через РМК (расходная накладная на кассе) закрывает
заявку (state -> done) и связывает документ продажи с заявкой.

См. также: :mod:`app.web.trade` (``/rmk/sell``), :mod:`app.services.document_service`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.security import create_access_token
from app.models.catalog import Nomenklatura, Sklad
from app.models.document.base_document import Document
from app.models.enums import DocType
from app.services import catalog_service, document_service, user_service


async def _zakaz_extra(seeded_session, zakaz_id: int) -> dict:
    """Свежее значение extra заявки (мимо identity-map)."""
    return (
        await seeded_session.execute(select(Document.extra).where(Document.id == zakaz_id))
    ).scalar_one()


async def test_rmk_sell_closes_zakaz(client, seeded_session):
    sklad = await catalog_service.create_one(
        seeded_session, Sklad, code="001", name="Склад", tip="optovy"
    )
    item = await catalog_service.create_one(
        seeded_session, Nomenklatura, code="001", name="Товар", vid="tovar"
    )
    prihod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PRIHOD,
        doc_date=date.today(),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("10"), "price": Decimal("100")}],
    )
    await document_service.post_document(seeded_session, prihod)

    zakaz = await document_service.create_document(
        seeded_session,
        doc_type=DocType.ZAKAZ,
        doc_date=date.today(),
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("2"), "price": Decimal("150")}],
        extra={"state": "new"},
    )

    user = await user_service.create_user(
        seeded_session, login="kassir2", password="secret123", is_admin=True
    )
    client.cookies.set("access_token", create_access_token(str(user.id)))

    resp = await client.post(
        "/rmk/sell",
        json={
            "sklad_id": sklad.id,
            "items": [{"nomenklatura_id": item.id, "quantity": 2, "price": 150}],
            "received": 300,
            "zakaz_id": zakaz.id,
        },
    )
    assert resp.status_code == 200
    sale_id = resp.json()["id"]

    # Заявка закрыта.
    assert (await _zakaz_extra(seeded_session, zakaz.id)).get("state") == "done"

    # Продажа — расходная накладная со ссылкой на заявку.
    sale = await document_service.get_document(seeded_session, sale_id)
    assert sale.doc_type == DocType.RASHOD.value
    assert sale.extra.get("zakaz_id") == zakaz.id


async def test_zakaz_reject_via_state(client, seeded_session):
    item = await catalog_service.create_one(
        seeded_session, Nomenklatura, code="001", name="Товар", vid="tovar"
    )
    zakaz = await document_service.create_document(
        seeded_session,
        doc_type=DocType.ZAKAZ,
        doc_date=date.today(),
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("1"), "price": Decimal("10")}],
        extra={"state": "new"},
    )
    user = await user_service.create_user(
        seeded_session, login="kassir3", password="secret123", is_admin=True
    )
    client.cookies.set("access_token", create_access_token(str(user.id)))

    resp = await client.post(f"/zakazy/{zakaz.id}/state", data={"state": "cancelled"})
    assert resp.status_code == 303
    assert (await _zakaz_extra(seeded_session, zakaz.id)).get("state") == "cancelled"
