"""Тесты чата покупателя интернет-магазина с продавцом.

См. также: :mod:`app.services.chat_service`, :mod:`app.customer.api`,
:mod:`app.models.messaging`.
"""
from __future__ import annotations

from sqlalchemy import select, text

from app.core.security import create_access_token
from app.models.customer import Customer
from app.models.messaging import Chat, Message


async def _register_customer(client, phone="+79991112233", name="Иван"):
    r = await client.post(
        "/shop/api/register",
        json={"phone": phone, "password": "secret123", "name": name},
    )
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _seller_headers(seeded_session, client):
    admin_id = (
        await seeded_session.execute(text("SELECT id FROM users WHERE is_admin = TRUE LIMIT 1"))
    ).scalar()
    client.cookies.set("access_token", create_access_token(str(admin_id)))


async def test_customer_send_message_creates_chat(client, seeded_session):
    headers = await _register_customer(client)
    r = await client.post("/shop/api/chat", json={"text": "Здравствуйте"}, headers=headers)
    assert r.status_code == 201
    assert r.json()["direction"] == "in"

    # Создан чат с каналом «site», привязанный к покупателю, с именем покупателя.
    chat = (await seeded_session.execute(select(Chat))).scalars().all()
    assert len(chat) == 1
    assert chat[0].channel == "site"
    assert chat[0].customer_id is not None
    assert chat[0].name == "Иван"

    msg = (await seeded_session.execute(select(Message))).scalars().all()
    assert len(msg) == 1
    assert msg[0].direction == "in"
    assert msg[0].text == "Здравствуйте"


async def test_customer_get_chat_messages(client, seeded_session):
    headers = await _register_customer(client)
    await client.post("/shop/api/chat", json={"text": "Привет"}, headers=headers)

    r = await client.get("/shop/api/chat", headers=headers)
    assert r.status_code == 200
    messages = r.json()["messages"]
    assert len(messages) == 1
    assert messages[0]["text"] == "Привет"
    assert messages[0]["direction"] == "in"


async def test_seller_sees_and_replies(client, seeded_session):
    headers = await _register_customer(client)
    await client.post("/shop/api/chat", json={"text": "Вопрос по заказу"}, headers=headers)

    # Продавец видит чат покупателя в общем списке.
    await _seller_headers(seeded_session, client)
    r = await client.get("/api/chats")
    chats = r.json()
    site_chats = [c for c in chats if c["channel"] == "site"]
    assert len(site_chats) == 1
    assert site_chats[0]["name"] == "Иван"

    chat_id = site_chats[0]["id"]
    # Продавец отвечает — сообщение direction="out".
    r = await client.post(f"/api/chats/{chat_id}/messages", json={"text": "Здравствуйте, чем помочь?"})
    assert r.status_code == 201
    assert r.json()["direction"] == "out"

    # Покупатель видит и свой вопрос, и ответ продавца.
    r = await client.get("/shop/api/chat", headers=headers)
    messages = r.json()["messages"]
    assert [m["direction"] for m in messages] == ["in", "out"]


async def test_empty_message_rejected(client, seeded_session):
    headers = await _register_customer(client)
    r = await client.post("/shop/api/chat", json={"text": "   "}, headers=headers)
    assert r.status_code == 400


async def test_chat_requires_auth(client, seeded_session):
    r = await client.get("/shop/api/chat")
    assert r.status_code == 401
    r = await client.post("/shop/api/chat", json={"text": "hi"})
    assert r.status_code == 401


async def test_chat_reuses_same_chat(client, seeded_session):
    headers = await _register_customer(client)
    await client.post("/shop/api/chat", json={"text": "Первое"}, headers=headers)
    await client.post("/shop/api/chat", json={"text": "Второе"}, headers=headers)

    chats = (await seeded_session.execute(select(Chat))).scalars().all()
    assert len(chats) == 1  # один чат на покупателя
    msgs = (await seeded_session.execute(select(Message).order_by(Message.id))).scalars().all()
    assert [m.text for m in msgs] == ["Первое", "Второе"]


async def test_operator_unread_count(client, seeded_session):
    """Непрочитанные входящие считаются для оператора и сбрасываются при просмотре."""
    headers = await _register_customer(client)
    await client.post("/shop/api/chat", json={"text": "Вопрос"}, headers=headers)

    await _seller_headers(seeded_session, client)
    r = await client.get("/api/chats/unread")
    assert r.status_code == 200
    assert r.json()["unread"] == 1
    assert r.json()["last"]["text"] == "Вопрос"

    # Оператор открывает чат → сообщение помечается прочитанным.
    chat_id = (await client.get("/api/chats")).json()[0]["id"]
    await client.get(f"/api/chats/{chat_id}/messages")
    r = await client.get("/api/chats/unread")
    assert r.json()["unread"] == 0


async def test_customer_unread_count(client, seeded_session):
    """Непрочитанные ответы продавца считаются для покупателя и сбрасываются при просмотре."""
    headers = await _register_customer(client)
    await client.post("/shop/api/chat", json={"text": "Вопрос"}, headers=headers)

    await _seller_headers(seeded_session, client)
    chat_id = (await client.get("/api/chats")).json()[0]["id"]
    await client.post(f"/api/chats/{chat_id}/messages", json={"text": "Ответ"})

    r = await client.get("/shop/api/chat/unread", headers=headers)
    assert r.json()["unread"] == 1

    # Покупатель открывает чат → ответ помечается прочитанным.
    await client.get("/shop/api/chat", headers=headers)
    r = await client.get("/shop/api/chat/unread", headers=headers)
    assert r.json()["unread"] == 0
