"""Тесты интеграции ботов: сервис, фабрика адаптеров, настройки.

См. также: :mod:`app.bots.service`, :mod:`app.bots.base`.
"""
from __future__ import annotations

from sqlalchemy import select

from app.bots.base import BotAdapter, IncomingMessage
from app.bots.service import (
    bot_manager,
    create_adapter,
    deliver_outgoing,
    find_or_create_chat,
    get_config,
    store_incoming,
    upsert_config,
)
from app.core.security import create_access_token
from app.models.messaging import Chat, Message
from app.services import user_service


class FakeAdapter(BotAdapter):
    """Заглушка адаптера для тестов."""

    channel = "telegram"

    def __init__(self) -> None:
        super().__init__(on_message=None)
        self.sent: list[tuple[str, str]] = []

    async def run(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def send_message(self, external_chat_id: str, text: str) -> None:
        self.sent.append((external_chat_id, text))


def test_create_adapter_factory():
    from app.bots.telegram import TelegramAdapter
    from app.bots.max import MaxAdapter

    # Валидный по формату токен (aiogram проверяет формат при создании).
    token = "1234567890:AAbbCCddEEffGGhhIIjjKKll"
    tg = create_adapter("telegram", token, None)
    mx = create_adapter("maks", token, None)
    assert isinstance(tg, TelegramAdapter)
    assert isinstance(mx, MaxAdapter)


def test_create_adapter_unknown_channel():
    import pytest

    with pytest.raises(ValueError):
        create_adapter("unknown", "fake", None)


async def test_find_or_create_chat(seeded_session):
    chat1 = await find_or_create_chat(seeded_session, "telegram", "123", "Иван")
    chat2 = await find_or_create_chat(seeded_session, "telegram", "123", "Иван")
    assert chat1.id == chat2.id  # повторный вызов не создаёт дубль


async def test_store_incoming(seeded_session):
    from app.core.database import async_session_factory

    msg = IncomingMessage(
        channel="telegram", external_chat_id="999", sender_name="Пётр", text="Привет"
    )
    await store_incoming(async_session_factory, msg)

    chat = (
        await seeded_session.execute(
            select(Chat).where(Chat.channel == "telegram", Chat.external_id == "999")
        )
    ).scalar_one()
    messages = (
        await seeded_session.execute(
            select(Message).where(Message.chat_id == chat.id)
        )
    ).scalars().all()
    assert len(messages) == 1
    assert messages[0].direction == "in"
    assert messages[0].text == "Привет"


async def test_deliver_outgoing_routes_to_adapter(seeded_session):
    adapter = FakeAdapter()
    bot_manager.register(adapter)
    chat = Chat(name="Клиент", channel="telegram", external_id="123")
    seeded_session.add(chat)
    await seeded_session.commit()

    await deliver_outgoing(chat, "Здравствуйте")
    assert adapter.sent == [("123", "Здравствуйте")]
    bot_manager.clear()


async def test_deliver_outgoing_no_adapter(seeded_session):
    """Без активного адаптера отправка не падает (только логируется)."""
    bot_manager.clear()
    chat = Chat(name="Клиент", channel="telegram", external_id="123")
    await deliver_outgoing(chat, "Привет")  # не должно бросать исключение


async def test_upsert_config_keeps_token_when_empty(seeded_session):
    await upsert_config(
        seeded_session, "telegram", enabled=True, token="secret-token", name="ТГ"
    )
    # Повторный вызов с пустым токеном не стирает его.
    await upsert_config(
        seeded_session, "telegram", enabled=False, token=None, name="ТГ"
    )
    cfg = await get_config(seeded_session, "telegram")
    assert cfg.token == "secret-token"
    assert cfg.enabled is False


async def test_admin_bots_page_renders(client, seeded_session):
    admin = (
        await seeded_session.execute(
            select(user_service.User).where(user_service.User.is_admin.is_(True))
        )
    ).scalars().first()
    client.cookies.set("access_token", create_access_token(str(admin.id)))
    resp = await client.get("/admin/bots")
    assert resp.status_code == 200
    assert "Telegram" in resp.text
    assert "MAX" in resp.text
