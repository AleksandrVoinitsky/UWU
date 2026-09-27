"""Тесты API, потребляемого AI-агентом (``/api/agent/*``).

Покрывают API-key аутентификацию, чтение конфигурации (промпты/инструменты),
обмен сообщениями, контекст покупателя, привязку по телефону, создание заказа
(система слотов), журнал запусков и tool-friendly чтение.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.catalog import Nomenklatura
from app.models.customer import Customer
from app.models.messaging import Chat, Message
from app.services import agent_service


@pytest.fixture
async def agent_headers(seeded_session):
    """Заголовок авторизации с валидным API-ключом агента."""
    key, raw = await agent_service.create_key(seeded_session, name="test-agent")
    assert key.permissions  # ключ по умолчанию получает права агента
    return {"Authorization": f"Bearer {raw}"}


# --- Аутентификация ------------------------------------------------------------


async def test_requires_api_key(client):
    resp = await client.get("/api/agent/prompts")
    assert resp.status_code == 401


async def test_rejects_invalid_key(client):
    resp = await client.get("/api/agent/prompts", headers={"Authorization": "Bearer uwu_bad"})
    assert resp.status_code == 401


# --- Конфигурация --------------------------------------------------------------


async def test_prompts(client, agent_headers):
    resp = await client.get("/api/agent/prompts", headers=agent_headers)
    assert resp.status_code == 200
    data = resp.json()
    keys = {p["key"] for p in data}
    assert {"system", "classify_intent", "generate", "reorder_suggestion"} <= keys
    system = next(p for p in data if p["key"] == "system")
    assert system["active_version"] == 1
    assert system["template"]


async def test_tools(client, agent_headers):
    resp = await client.get("/api/agent/tools", headers=agent_headers)
    assert resp.status_code == 200
    data = resp.json()
    keys = {t["key"] for t in data}
    assert {"search_catalog", "get_stock", "get_cart", "get_order_status"} <= keys


# --- Сообщения -----------------------------------------------------------------


async def test_inbox_returns_unread(client, agent_headers, seeded_session):
    chat = Chat(name="Покупатель", channel="site")
    seeded_session.add(chat)
    await seeded_session.flush()
    seeded_session.add(Message(chat_id=chat.id, direction="in", text="Есть в наличии?", author="customer"))
    await seeded_session.commit()

    resp = await client.get("/api/agent/inbox", headers=agent_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["text"] == "Есть в наличии?"
    assert data[0]["chat_id"] == chat.id


async def test_post_message_as_agent(client, agent_headers, seeded_session):
    chat = Chat(name="Покупатель", channel="site")
    seeded_session.add(chat)
    await seeded_session.flush()
    await seeded_session.commit()

    resp = await client.post(
        "/api/agent/messages",
        headers=agent_headers,
        json={"chat_id": chat.id, "text": "Да, 5 штук.", "author": "agent"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["author"] == "agent"
    assert data["direction"] == "out"
    assert data["text"] == "Да, 5 штук."


async def test_post_message_missing_chat(client, agent_headers):
    resp = await client.post(
        "/api/agent/messages", headers=agent_headers, json={"chat_id": 9999, "text": "x"}
    )
    assert resp.status_code == 404


# --- Контекст ------------------------------------------------------------------


async def test_context_with_customer(client, agent_headers, seeded_session):
    customer = Customer(phone="79990000001", password_hash="x", name="Иван")
    seeded_session.add(customer)
    await seeded_session.flush()
    chat = Chat(name="Иван", channel="site", customer_id=customer.id)
    seeded_session.add(chat)
    await seeded_session.commit()

    resp = await client.get(f"/api/agent/context/{chat.id}", headers=agent_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["chat"]["channel"] == "site"
    assert data["customer"]["name"] == "Иван"
    assert data["cart"] == []


async def test_context_missing_chat(client, agent_headers):
    resp = await client.get("/api/agent/context/9999", headers=agent_headers)
    assert resp.status_code == 404


# --- Привязка покупателя по телефону и создание заказа --------------------------


async def test_match_customer_not_found(client, agent_headers):
    resp = await client.get(
        "/api/agent/match_customer", headers=agent_headers, params={"phone": "+79990000000"}
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is False


async def test_match_customer_found_by_kontragent(client, agent_headers, seeded_session):
    from app.models.catalog import Kontragent

    seeded_session.add(Kontragent(code="K001", name="Иван", phones="+79991112233"))
    await seeded_session.commit()

    resp = await client.get(
        "/api/agent/match_customer", headers=agent_headers, params={"phone": "79991112233"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is True
    assert data["name"] == "Иван"
    assert data["kontragent_id"] is not None


async def test_create_order_requires_phone(client, agent_headers):
    resp = await client.post(
        "/api/agent/create_order",
        headers=agent_headers,
        json={"customer_phone": "", "items": [{"name": "хлеб", "quantity": 2}]},
    )
    assert resp.status_code == 200
    assert resp.json()["created"] is False
    assert "телефон" in resp.json()["error"].lower()


async def test_create_order_auto_registers_new_phone(client, agent_headers, seeded_session):
    """Новый номер автоматически создаёт контрагента + аккаунт, связанные по номеру."""
    from sqlalchemy import select

    from app.models.catalog import Kontragent, Nomenklatura

    seeded_session.add(Nomenklatura(code="901", name="Хлеб пшеничный", retail_price=Decimal("45.00")))
    await seeded_session.commit()

    resp = await client.post(
        "/api/agent/create_order",
        headers=agent_headers,
        json={
            "customer_phone": "+79995556677",
            "customer_name": "Иван",
            "items": [{"name": "хлеб пшеничный", "quantity": 2}],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] is True

    # Авто-регистрация: контрагент и аккаунт созданы и связаны (Customer.kontragent_id).
    kg = (
        await seeded_session.execute(select(Kontragent).where(Kontragent.phones == "79995556677"))
    ).scalar_one()
    customer = (
        await seeded_session.execute(select(Customer).where(Customer.phone == "79995556677"))
    ).scalar_one()
    assert customer.kontragent_id == kg.id
    assert kg.name == "Иван"


async def test_create_order_by_name(client, agent_headers, seeded_session):
    from app.models.catalog import Kontragent, Nomenklatura

    seeded_session.add(Kontragent(code="K002", name="Пётр", phones="+79992223344"))
    seeded_session.add(Nomenklatura(code="900", name="Хлеб пшеничный", retail_price=Decimal("45.00")))
    await seeded_session.commit()

    resp = await client.post(
        "/api/agent/create_order",
        headers=agent_headers,
        json={
            "customer_phone": "+79992223344",
            "items": [{"name": "хлеб пшеничный", "quantity": 2}],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] is True
    assert data["order"]["items"][0]["name"] == "Хлеб пшеничный"
    assert Decimal(str(data["order"]["items"][0]["quantity"])) == 2


# --- Журнал запусков -----------------------------------------------------------


async def test_create_run(client, agent_headers):
    resp = await client.post(
        "/api/agent/runs",
        headers=agent_headers,
        json={"trace_id": "tr-1", "intent": "stock", "model": "gpt-4.1", "status": "ok"},
    )
    assert resp.status_code == 201
    assert resp.json()["trace_id"] == "tr-1"


# --- Tool-friendly чтение ------------------------------------------------------


async def test_search_catalog(client, agent_headers, seeded_session):
    seeded_session.add(Nomenklatura(code="001", name="Ручка", retail_price=Decimal("100.00")))
    await seeded_session.commit()

    resp = await client.get("/api/agent/search_catalog", headers=agent_headers, params={"query": "руч"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Ручка"
    assert data[0]["stock"] == "0"


async def test_get_stock_empty(client, agent_headers, seeded_session):
    n = Nomenklatura(code="002", name="Тетрадь")
    seeded_session.add(n)
    await seeded_session.commit()

    resp = await client.get("/api/agent/get_stock", headers=agent_headers, params={"nomenklatura_id": n.id})
    assert resp.status_code == 200
    assert resp.json()["balance"] == "0"
    assert resp.json()["available"] == "0"


async def test_get_cart_empty(client, agent_headers, seeded_session):
    customer = Customer(phone="79990000002", password_hash="x")
    seeded_session.add(customer)
    await seeded_session.commit()

    resp = await client.get("/api/agent/get_cart", headers=agent_headers, params={"customer_id": customer.id})
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["total"] == "0.00"


async def test_get_zakaz_missing(client, agent_headers):
    resp = await client.get("/api/agent/get_zakaz", headers=agent_headers, params={"order_id": 9999})
    assert resp.status_code == 404
