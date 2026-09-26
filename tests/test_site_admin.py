"""Тесты управления сайтом/MiniApp и уведомлений каталога.

Покрывают: настройки сайта, акции (скидки, приоритет, применение), публикацию
товаров (фильтр каталога), интеграцию цены со скидкой и страницы админки.

См. также: :mod:`app.services.site_service`, :mod:`app.web.site_admin`,
:mod:`app.services.customer_service`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.catalog import Nomenklatura, Sklad
from app.models.enums import DocType
from app.models.site import Promotion
from app.models.users import Role
from app.services import (
    catalog_service,
    customer_service,
    document_service,
    site_service,
    user_service,
)
from app.core.security import create_access_token


# --- Настройки ----------------------------------------------------------------


async def test_site_settings_defaults_and_set(seeded_session):
    s = await site_service.get_settings(seeded_session)
    assert s["card_style"] == "grid"
    assert s["show_prices"] is True

    await site_service.set_settings(
        seeded_session, {"card_style": "list", "show_prices": False}
    )
    s = await site_service.get_settings(seeded_session)
    assert s["card_style"] == "list"
    assert s["show_prices"] is False


# --- Акции --------------------------------------------------------------------


def test_apply_discount_percent():
    promo = Promotion(discount_type="percent", value=Decimal("20"))
    assert site_service.apply_discount(Decimal("100"), promo) == Decimal("80.00")


def test_apply_discount_fixed_not_below_zero():
    promo = Promotion(discount_type="fixed", value=Decimal("30"))
    assert site_service.apply_discount(Decimal("100"), promo) == Decimal("70.00")
    assert site_service.apply_discount(Decimal("10"), promo) == Decimal("0.00")


def test_find_promotion_priority():
    promos = [
        Promotion(name="global", discount_type="percent", value=Decimal("10"), enabled=True),
        Promotion(name="cat", discount_type="percent", value=Decimal("20"), category_id=5, enabled=True),
        Promotion(name="item", discount_type="percent", value=Decimal("30"), nomenklatura_id=1, enabled=True),
    ]
    assert site_service.find_promotion(promos, 1, 5).name == "item"
    assert site_service.find_promotion(promos, 2, 5).name == "cat"
    assert site_service.find_promotion(promos, 2, None).name == "global"


async def test_promotion_crud_and_toggle(seeded_session):
    promo = await site_service.create_promotion(
        seeded_session, name="Распродажа", discount_type="percent", value=Decimal("15")
    )
    assert promo.enabled is True

    await site_service.update_promotion(seeded_session, promo, enabled=False)
    assert (await site_service.get_promotion(seeded_session, promo.id)).enabled is False

    await site_service.delete_promotion(seeded_session, promo)
    assert await site_service.get_promotion(seeded_session, promo.id) is None


# --- Каталог: публикация + акции ----------------------------------------------


async def _seed_stock(seeded_session):
    sklad = await catalog_service.create_one(
        seeded_session, Sklad, code="001", name="Склад", tip="optovy"
    )
    return sklad


async def test_catalog_filters_unpublished_and_applies_promo(seeded_session):
    sklad = await _seed_stock(seeded_session)
    item1 = await catalog_service.create_one(
        seeded_session, Nomenklatura, code="001", name="Видимый", vid="tovar",
        retail_price=Decimal("100"), is_published=True,
    )
    item2 = await catalog_service.create_one(
        seeded_session, Nomenklatura, code="002", name="Скрытый", vid="tovar",
        retail_price=Decimal("50"), is_published=False,
    )
    for it, price in [(item1, Decimal("100")), (item2, Decimal("50"))]:
        prihod = await document_service.create_document(
            seeded_session,
            doc_type=DocType.PRIHOD,
            doc_date=date.today(),
            sklad_id=sklad.id,
            items=[{"nomenklatura_id": it.id, "quantity": Decimal("10"), "price": price}],
        )
        await document_service.post_document(seeded_session, prihod)

    await site_service.create_promotion(
        seeded_session, name="Скидка", discount_type="percent", value=Decimal("10")
    )

    products = await customer_service.available_products(seeded_session)
    names = {p["name"] for p in products}
    assert "Видимый" in names
    assert "Скрытый" not in names  # не опубликован

    p1 = next(p for p in products if p["name"] == "Видимый")
    assert p1["price"] == Decimal("90.00")
    assert p1["price_old"] == Decimal("100")
    assert p1["promo_name"] == "Скидка"


# --- Админка ------------------------------------------------------------------


async def test_site_admin_renders(client, seeded_session, admin_token):
    client.cookies.set("access_token", admin_token)
    resp = await client.get("/admin/site")
    assert resp.status_code == 200
    assert "Логотип фирмы" in resp.text
    assert "Акции" in resp.text
    assert "Товары на сайте" in resp.text


async def test_site_admin_requires_admin(client, seeded_session):
    role = (await seeded_session.execute(select(Role).where(Role.key == "operator"))).scalar_one()
    user = await user_service.create_user(
        seeded_session, login="siteop", password="secret123", role_id=role.id
    )
    client.cookies.set("access_token", create_access_token(str(user.id)))
    resp = await client.get("/admin/site")
    assert resp.status_code == 303


async def test_toggle_product_publish(client, seeded_session, admin_token):
    item = await catalog_service.create_one(
        seeded_session, Nomenklatura, code="001", name="Товар", vid="tovar", is_published=True
    )
    client.cookies.set("access_token", admin_token)
    resp = await client.post(f"/admin/site/products/{item.id}/toggle")
    assert resp.status_code == 303
    # Маршрут использует другую сессию — читаем значение свежим запросом.
    published = (
        await seeded_session.execute(
            select(Nomenklatura.is_published).where(Nomenklatura.id == item.id)
        )
    ).scalar_one()
    assert published is False


async def test_create_promotion_via_route(client, seeded_session, admin_token):
    client.cookies.set("access_token", admin_token)
    resp = await client.post(
        "/admin/site/promotions",
        data={"name": "Тест", "discount_type": "percent", "value": "20"},
    )
    assert resp.status_code == 303
    promos = await site_service.list_promotions(seeded_session)
    assert any(p.name == "Тест" for p in promos)


# --- Изображения (WebP без фона) ----------------------------------------------


def test_detect_webp_transparent():
    from app.services import image_service

    webp = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 24
    assert image_service.detect_ext(webp) == ".webp"


def test_detect_rejects_wav_riff():
    from app.services import image_service

    wav = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 24
    assert image_service.detect_ext(wav) is None


def test_detect_png():
    from app.services import image_service

    assert image_service.detect_ext(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20) == ".png"
