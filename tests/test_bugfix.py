"""Регрессионные тесты багфикса (см. docs/bugfix.md).

Каждый тест закрепляет конкретный исправленный дефект, чтобы он не вернулся.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.security import create_access_token
from app.models.catalog import Kassa, Kontragent, Nomenklatura, Sklad
from app.models.enums import CostMethod, DocSubtype, DocType
from app.services import (
    cash_service,
    catalog_service,
    customer_service,
    document_service,
    miniapp_service,
    report_service,
    stock_service,
    user_service,
)
from app.services.customer_service import CustomerError


# --- C2: next_code не «застревает» на 1000 ---


async def test_next_code_crosses_999(seeded_session):
    await catalog_service.create_one(seeded_session, Nomenklatura, code="999", name="X", vid="tovar")
    c1 = await catalog_service.next_nomenklatura_code(seeded_session)
    assert c1 == "1000"
    await catalog_service.create_one(seeded_session, Nomenklatura, code=c1, name="Y", vid="tovar")
    c2 = await catalog_service.next_nomenklatura_code(seeded_session)
    assert c2 == "1001"


# --- C3: префиксы номеров документов не пересекаются ---


async def test_document_number_prefix_no_collision(seeded_session):
    n1 = await document_service.next_document_number(seeded_session, DocType.PEREOCENKA)
    n2 = await document_service.next_document_number(seeded_session, DocType.PEREMESHENIE)
    assert n1 != n2

    n3 = await document_service.next_document_number(seeded_session, DocType.VVOD_OSTATKOV)
    n4 = await document_service.next_document_number(seeded_session, DocType.VVOD_OSTATKOV_DENEG)
    assert n3 != n4


# --- C5: метод AVERAGE при нулевом количестве не делит на ноль ---


async def test_consume_average_zero_quantity(seeded_session):
    await catalog_service.set_constant(seeded_session, "cost_method", "average")
    consumed, amount = await stock_service.consume_batches(
        seeded_session,
        nomenklatura_id=999999,
        sklad_id=999999,
        quantity=Decimal("0"),
        method=CostMethod.AVERAGE,
    )
    assert consumed == []
    assert amount == Decimal("0")


# --- C1: X/Z-отчёт учитывает только движения своей кассы ---


async def test_shift_revenue_filters_kassa(seeded_session):
    kassa_a = await catalog_service.create_one(seeded_session, Kassa, name="Касса A")
    kassa_b = await catalog_service.create_one(seeded_session, Kassa, name="Касса B")

    shift = await cash_service.open_shift(
        seeded_session, kassa_id=kassa_a.id, opening_amount=Decimal("0"), user_id=None
    )

    # ПКО на кассу B — движение денег +100 не по кассе A.
    doc = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PRIHODNY_KASSOVY_ORDER,
        doc_date=date.today(),
        kassa_id=kassa_b.id,
        total=Decimal("100"),
    )
    await document_service.post_document(seeded_session, doc)

    # Выручка смены кассы A не должна учитывать движение кассы B.
    assert await cash_service.shift_revenue(seeded_session, shift) == Decimal("0")


# --- C4: долг комитентам — только по принятым на реализацию ---


async def test_commission_debt_excludes_credit_prihod(seeded_session):
    item = await catalog_service.create_one(seeded_session, Nomenklatura, code="001", name="Товар", vid="tovar")
    sklad = await catalog_service.create_one(seeded_session, Sklad, code="001", name="Склад", tip="optovy")
    kg = await catalog_service.create_one(seeded_session, Kontragent, code="001", name="Поставщик")

    # Кредитный приход создаёт отрицательное взаиморасчётное движение (долг
    # поставщику), но это НЕ комиссия — долг комитентам должен остаться нулевым.
    prihod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PRIHOD,
        subtype=DocSubtype.CREDIT,
        doc_date=date.today(),
        sklad_id=sklad.id,
        kontragent_id=kg.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("1"), "price": Decimal("500")}],
    )
    await document_service.post_document(seeded_session, prihod)

    report = await report_service.commission_report(seeded_session)
    assert report["debt"] == Decimal("0")


# --- B3: синтетический телефон MiniApp помещается в колонку ---


async def test_find_or_create_customer_long_external_id(seeded_session):
    customer = await miniapp_service.find_or_create_customer(
        seeded_session, "telegram", "279058397", "Иван"
    )
    assert customer.phone == "ma_telegram_279058397"


# --- B4: слишком длинный телефон отклоняется (а не падает на длине колонки) ---


async def test_register_phone_too_long(seeded_session):
    with pytest.raises(CustomerError):
        await customer_service.register(seeded_session, "1" * 100, "secret123")


# --- A4: rmk_sell с невалидной строкой возвращает 400, а не 500 ---


async def test_rmk_sell_invalid_item_returns_400(client, seeded_session):
    user = await user_service.create_user(
        seeded_session, login="kassir", password="secret123", is_admin=True
    )
    client.cookies.set("access_token", create_access_token(str(user.id)))

    # Нет цены.
    r = await client.post("/rmk/sell", json={"items": [{"nomenklatura_id": 1, "quantity": 1}]})
    assert r.status_code == 400
    # Нечисловая цена.
    r2 = await client.post(
        "/rmk/sell", json={"items": [{"nomenklatura_id": 1, "quantity": 1, "price": "abc"}]}
    )
    assert r2.status_code == 400


# --- A6/D1: дубль/пустой логин при создании пользователя не роняет 500 ---


async def _admin_cookie(client, seeded_session):
    admin_id = (
        await seeded_session.execute(text("SELECT id FROM users WHERE is_admin = TRUE LIMIT 1"))
    ).scalar()
    client.cookies.set("access_token", create_access_token(str(admin_id)))


async def test_admin_create_duplicate_login_no_500(client, seeded_session):
    await _admin_cookie(client, seeded_session)
    r1 = await client.post("/admin/users", data={"login": "dup", "password": "secret1"})
    assert r1.status_code == 303
    r2 = await client.post("/admin/users", data={"login": "dup", "password": "secret2"})
    assert r2.status_code == 303  # не 500
    cnt = (
        await seeded_session.execute(text("SELECT count(*) FROM users WHERE login = 'dup'"))
    ).scalar()
    assert cnt == 1


async def test_admin_create_empty_login_no_500(client, seeded_session):
    await _admin_cookie(client, seeded_session)
    r = await client.post("/admin/users", data={"login": "", "password": "secret1"})
    assert r.status_code == 303  # не 500
    cnt = (
        await seeded_session.execute(text("SELECT count(*) FROM users WHERE login = ''"))
    ).scalar()
    assert cnt == 0
