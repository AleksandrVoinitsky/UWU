"""Тесты MiniApp: валидация initData, привязка, вход.

См. также: :mod:`app.services.miniapp_service`, :mod:`app.customer.miniapp`.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models.customer import Customer, CustomerBinding
from app.services import miniapp_service

TG_TOKEN = "1234567890:AAbbCCddEEffGGhhIIjjKKll"


# --- Валидация подписи initData ---


def test_telegram_init_data_roundtrip():
    data = miniapp_service.make_test_init_data("telegram", TG_TOKEN, 42, "Иван")
    info = miniapp_service.validate_init_data("telegram", data, TG_TOKEN)
    assert info is not None
    assert info["external_id"] == "42"
    assert info["name"] == "Иван"


def test_telegram_init_data_wrong_secret():
    data = miniapp_service.make_test_init_data("telegram", TG_TOKEN, 42, "Иван")
    info = miniapp_service.validate_init_data("telegram", data, "9999999999:WRONG")
    assert info is None


def test_telegram_init_data_garbage():
    assert miniapp_service.validate_init_data("telegram", "foo=bar", TG_TOKEN) is None


def test_max_init_data_roundtrip():
    data = miniapp_service.make_test_init_data("maks", "max-secret", 7)
    info = miniapp_service.validate_init_data("maks", data, "max-secret")
    assert info is not None
    assert info["external_id"] == "7"


# --- Привязка к покупателю ---


async def test_find_or_create_customer(seeded_session):
    c1 = await miniapp_service.find_or_create_customer(
        seeded_session, "telegram", "123", "Иван"
    )
    # Повторный вызов возвращает того же покупателя.
    c2 = await miniapp_service.find_or_create_customer(
        seeded_session, "telegram", "123", "Иван"
    )
    assert c1.id == c2.id

    bindings = (
        await seeded_session.execute(select(CustomerBinding))
    ).scalars().all()
    assert len(bindings) == 1
    assert bindings[0].channel == "telegram"
    assert bindings[0].external_id == "123"

    customer = await seeded_session.get(Customer, c1.id)
    assert customer.phone == "ma_telegram_123"


# --- Точка входа (dev-режим) ---


async def test_mini_entry_dev_mode(client, seeded_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "miniapp_dev", True)
    resp = await client.get(
        "/shop/mini", params={"channel": "telegram", "user_id": "123", "name": "Иван"}
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/shop/"
    assert resp.cookies.get("customer_token")

    binding = (
        await seeded_session.execute(select(CustomerBinding))
    ).scalars().all()
    assert len(binding) == 1
    assert binding[0].external_id == "123"
