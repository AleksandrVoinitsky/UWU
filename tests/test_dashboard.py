"""Тесты сводных показателей дашборда.

См. также: :mod:`app.services.report_service`, :mod:`app.web.trade`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.catalog import Kontragent, Nomenklatura, Sklad
from app.models.enums import DocType
from app.services import catalog_service, document_service, report_service, user_service
from app.core.security import create_access_token


async def _seed_sale(seeded_session):
    """Создаёт товар, склад, клиента и проведённую продажу (5 шт по 300, себест. 100)."""
    item = await catalog_service.create_one(
        seeded_session, Nomenklatura, code="001", name="Товар А", vid="tovar"
    )
    sklad = await catalog_service.create_one(
        seeded_session, Sklad, code="001", name="Склад", tip="optovy"
    )
    client = await catalog_service.create_one(
        seeded_session, Kontragent, code="001", name="ООО Покупатель"
    )
    prihod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PRIHOD,
        doc_date=date(2025, 1, 1),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("10"), "price": Decimal("100")}],
    )
    await document_service.post_document(seeded_session, prihod)

    rashod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.RASHOD,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad.id,
        kontragent_id=client.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("5"), "price": Decimal("300")}],
    )
    await document_service.post_document(seeded_session, rashod)
    return item, sklad, client, prihod, rashod


async def test_sales_summary(seeded_session):
    await _seed_sale(seeded_session)
    summary = await report_service.sales_summary(
        seeded_session, date(2025, 1, 1), date(2025, 1, 31)
    )
    assert summary["revenue"] == Decimal("1500")
    assert summary["profit"] == Decimal("1000")  # 1500 - 500 (5 * 100)
    assert summary["cost"] == Decimal("500")
    assert summary["orders_count"] == 1
    assert summary["avg_check"] == Decimal("1500")
    assert summary["purchases"] == Decimal("1000")  # 10 * 100


async def test_daily_sales_fills_zero_days(seeded_session):
    await _seed_sale(seeded_session)
    rows = await report_service.daily_sales(
        seeded_session, date(2025, 1, 1), date(2025, 1, 5)
    )
    assert len(rows) == 5
    by_date = {r["date"]: r for r in rows}
    # 1 января — только закупка, продаж нет.
    assert by_date["2025-01-01"]["revenue"] == Decimal("0")
    # 2 января — продажа.
    assert by_date["2025-01-02"]["revenue"] == Decimal("1500")
    assert by_date["2025-01-02"]["profit"] == Decimal("1000")
    # 3 января — пустой день.
    assert by_date["2025-01-03"]["revenue"] == Decimal("0")


async def test_top_items(seeded_session):
    await _seed_sale(seeded_session)
    rows = await report_service.top_items(seeded_session, date(2025, 1, 1), date(2025, 1, 31))
    assert len(rows) == 1
    assert rows[0]["name"] == "Товар А"
    assert rows[0]["quantity"] == Decimal("5")
    assert rows[0]["amount"] == Decimal("1500")


async def test_top_counterparties(seeded_session):
    await _seed_sale(seeded_session)
    rows = await report_service.top_counterparties(
        seeded_session, date(2025, 1, 1), date(2025, 1, 31)
    )
    assert len(rows) == 1
    assert rows[0]["name"] == "ООО Покупатель"
    assert rows[0]["amount"] == Decimal("1500")


async def test_low_stock(seeded_session):
    await _seed_sale(seeded_session)  # осталось 5 шт (из 10).
    rows = await report_service.low_stock(seeded_session, threshold=5)
    names = {r["name"] for r in rows}
    assert "Товар А" in names
    stock = next(r for r in rows if r["name"] == "Товар А")
    assert stock["quantity"] == Decimal("5")


async def test_recent_sales(seeded_session):
    _, _, _, _, rashod = await _seed_sale(seeded_session)
    rows = await report_service.recent_sales(seeded_session)
    assert len(rows) == 1
    assert rows[0]["number"] == rashod.number
    assert rows[0]["total"] == Decimal("1500")
    assert rows[0]["profit"] == Decimal("1000")


async def test_dashboard_route_renders(client, seeded_session):
    """Главная рендерится для обычного пользователя и содержит график и метрики."""
    await _seed_sale(seeded_session)
    user = await user_service.create_user(
        seeded_session, login="operator1", password="secret123", full_name="Оператор"
    )
    client.cookies.set("access_token", create_access_token(str(user.id)))
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "daily-chart" in resp.text  # график по дням
    assert "Выручка" in resp.text
    assert "Топ товаров" in resp.text


async def test_dashboard_route_period_param(client, seeded_session):
    """Параметр period принимается без ошибок."""
    await _seed_sale(seeded_session)
    user = await user_service.create_user(
        seeded_session, login="operator2", password="secret123"
    )
    client.cookies.set("access_token", create_access_token(str(user.id)))
    resp = await client.get("/?period=30d")
    assert resp.status_code == 200
    resp2 = await client.get("/?start=2025-01-01&end=2025-01-31")
    assert resp2.status_code == 200
