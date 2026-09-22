"""Тесты клиентского сайта: аккаунты, каталог, корзина, заказ, PDF.

См. также: :mod:`app.services.customer_service`, :mod:`app.customer.api`,
:mod:`app.core.security`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.security import (
    create_access_token,
    create_customer_token,
    decode_access_token,
    decode_customer_token,
)
from app.models.catalog import Category, Kontragent, Nomenklatura, Sklad
from app.models.customer import Customer
from app.models.document.base_document import Document
from app.models.enums import DocType
from app.services import catalog_service, customer_service, document_service


# --- Разделение токенов сотрудников и покупателей ---


def test_customer_token_is_not_employee_token():
    token = create_customer_token(1)
    assert decode_customer_token(token) == 1
    assert decode_access_token(token) is None  # нельзя войти как сотрудник


def test_employee_token_is_not_customer_token():
    token = create_access_token("1")
    assert decode_customer_token(token) is None


# --- Регистрация и вход (через API) ---


async def test_register_and_login(client, seeded_session):
    r = await client.post(
        "/shop/api/register", json={"phone": "+79991112233", "password": "secret123", "name": "Иван"}
    )
    assert r.status_code == 201
    token = r.json()["access_token"]

    r = await client.post("/shop/api/login", json={"phone": "+79991112233", "password": "secret123"})
    assert r.status_code == 200
    assert r.json()["access_token"]

    h = {"Authorization": f"Bearer {token}"}
    r = await client.get("/shop/api/me", headers=h)
    assert r.status_code == 200
    assert r.json()["phone"] == "+79991112233"


async def test_register_duplicate_phone(client, seeded_session):
    await client.post("/shop/api/register", json={"phone": "+79990000000", "password": "secret123"})
    r = await client.post("/shop/api/register", json={"phone": "+79990000000", "password": "secret123"})
    assert r.status_code == 400


async def test_customer_login_wrong_password(client, seeded_session):
    await client.post("/shop/api/register", json={"phone": "+79991112233", "password": "secret123"})
    r = await client.post("/shop/api/login", json={"phone": "+79991112233", "password": "wrong"})
    assert r.status_code == 401


# --- Каталог (в наличии) ---


async def _seed_in_stock_item(seeded_session, name="Товар", price="500", qty="10"):
    code = await catalog_service.next_nomenklatura_code(seeded_session)
    item = await catalog_service.create_one(
        seeded_session, Nomenklatura, code=code, name=name, vid="tovar", retail_price=Decimal(price)
    )
    sklad = await catalog_service.create_one(
        seeded_session, Sklad, code="", name="Склад", tip="optovy"
    )
    prihod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PRIHOD,
        doc_date=date.today(),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal(qty), "price": Decimal("100")}],
    )
    await document_service.post_document(seeded_session, prihod)
    return item


async def test_products_only_in_stock(client, seeded_session):
    await _seed_in_stock_item(seeded_session, name="В наличии", qty="5")
    code = await catalog_service.next_nomenklatura_code(seeded_session)
    out = await catalog_service.create_one(
        seeded_session, Nomenklatura, code=code, name="Нет на складе", vid="tovar", retail_price=Decimal("100")
    )
    r = await client.get("/shop/api/products")
    assert r.status_code == 200
    names = {p["name"] for p in r.json()}
    assert "В наличии" in names
    assert "Нет на складе" not in names


async def test_categories_list(client, seeded_session):
    await catalog_service.create_one(seeded_session, Category, name="Электроника", sort=1)
    r = await client.get("/shop/api/categories")
    assert r.status_code == 200
    names = {c["name"] for c in r.json()}
    assert "Электроника" in names


# --- Корзина и заказ ---


async def test_cart_and_checkout(client, seeded_session):
    item = await _seed_in_stock_item(seeded_session, name="Телефон", price="1000", qty="10")
    r = await client.post("/shop/api/register", json={"phone": "+79990001122", "password": "secret123"})
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # Добавить в корзину.
    r = await client.post("/shop/api/cart", json={"nomenklatura_id": item.id, "quantity": 2}, headers=h)
    assert r.status_code == 201
    cart = r.json()
    assert float(cart["total"]) == 2000.00
    assert len(cart["items"]) == 1

    # Оформить заказ.
    r = await client.post("/shop/api/checkout", headers=h)
    assert r.status_code == 201
    order = r.json()
    assert float(order["total"]) == 2000.00
    assert len(order["items"]) == 1

    # Корзина очистилась.
    r = await client.get("/shop/api/cart", headers=h)
    assert r.json()["items"] == []

    # Создана заявка покупателя (ZAKAZ).
    doc = (
        await seeded_session.execute(select(Document).where(Document.number == order["number"]))
    ).scalar_one()
    assert doc.doc_type == DocType.ZAKAZ.value
    assert doc.extra["customer_phone"] == "+79990001122"
    assert doc.extra["source"] == "customer"


async def test_checkout_matches_kontragent_by_phone(client, seeded_session):
    item = await _seed_in_stock_item(seeded_session, name="Товар", price="100", qty="5")
    kg = await catalog_service.create_one(
        seeded_session, Kontragent, code="", name="ООО Клиент", phones="+79990001122"
    )
    r = await client.post("/shop/api/register", json={"phone": "+79990001122", "password": "secret123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    await client.post("/shop/api/cart", json={"nomenklatura_id": item.id, "quantity": 1}, headers=h)
    r = await client.post("/shop/api/checkout", headers=h)
    assert r.status_code == 201

    doc = (
        await seeded_session.execute(
            select(Document).where(Document.number == r.json()["number"])
        )
    ).scalar_one()
    assert doc.kontragent_id == kg.id  # контрагент идентифицирован по телефону


async def test_checkout_empty_cart(client, seeded_session):
    r = await client.post("/shop/api/register", json={"phone": "+79995556677", "password": "secret123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = await client.post("/shop/api/checkout", headers=h)
    assert r.status_code == 400  # пустая корзина


# --- PDF (HTML всегда; PDF — если доступен WeasyPrint) ---


async def test_order_pdf_html(client, seeded_session):
    item = await _seed_in_stock_item(seeded_session, name="Товар", price="100", qty="5")
    r = await client.post("/shop/api/register", json={"phone": "+79990009999", "password": "secret123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    await client.post("/shop/api/cart", json={"nomenklatura_id": item.id, "quantity": 1}, headers=h)
    order = (await client.post("/shop/api/checkout", headers=h)).json()

    from app.services import pdf_service

    html = pdf_service.render_order_html(order)
    assert order["number"] in html
    assert "Товар" in html
