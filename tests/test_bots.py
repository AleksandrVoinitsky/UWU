"""Тесты интеграции ботов: сервис, фабрика адаптеров, настройки.

См. также: :mod:`app.bots.service`, :mod:`app.bots.base`.
"""
from __future__ import annotations

from sqlalchemy import select

from app.bots.base import BotAdapter, IncomingMessage, strip_markdown
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


async def test_telegram_adapter_retries_on_polling_error(monkeypatch):
    """При сетевом сбое long polling перезапускается, а не «умирает» молча."""
    from app.bots.telegram import TelegramAdapter
    import app.bots.telegram as tg_mod

    token = "1234567890:AAbbCCddEEffGGhhIIjjKKll"
    calls = 0

    adapter = TelegramAdapter(token, on_message=None)

    async def fake_start_polling(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("network down")
        adapter._stopped = True  # третий вызов — штатная остановка

    monkeypatch.setattr(adapter._dp, "start_polling", fake_start_polling)
    monkeypatch.setattr(tg_mod, "_RETRY_DELAY", 0)

    await adapter.run()

    assert calls == 3  # два сбоя + успешный третий запуск (затем остановка)


async def test_find_or_create_chat(seeded_session):
    chat1 = await find_or_create_chat(seeded_session, "telegram", "123", "Иван")
    chat2 = await find_or_create_chat(seeded_session, "telegram", "123", "Иван")
    assert chat1.id == chat2.id  # повторный вызов не создаёт дубль


async def test_chat_unique_channel_external(seeded_session):
    """Уникальное ограничение (channel, external_id) не даёт создать дубль чата."""
    from sqlalchemy.exc import IntegrityError
    import pytest

    await find_or_create_chat(seeded_session, "telegram", "456", "Иван")
    dup = Chat(name="Дубль", channel="telegram", external_id="456")
    seeded_session.add(dup)
    with pytest.raises(IntegrityError):
        await seeded_session.flush()
    await seeded_session.rollback()


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
    assert messages[0].author == "customer"  # входящее — от покупателя


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


def test_strip_markdown():
    """Разметка Markdown убирается в обычный текст (для мессенджеров)."""
    assert strip_markdown("**Жирный** текст") == "Жирный текст"
    assert strip_markdown("*курсив* и _ещё_") == "курсив и ещё"
    assert strip_markdown("- пункт 1\n- пункт 2") == "• пункт 1\n• пункт 2"
    assert strip_markdown("## Заголовок") == "Заголовок"
    assert strip_markdown("Ссылка [тут](http://x) и `код`") == "Ссылка тут и код"
    assert strip_markdown("1. Первый\n2. Второй") == "Первый\nВторой"
    assert strip_markdown("") == ""


async def test_deliver_outgoing_strips_markdown(seeded_session):
    """Ответ агенту доставляется в мессенджер без Markdown-разметки."""
    adapter = FakeAdapter()
    bot_manager.register(adapter)
    chat = Chat(name="Клиент", channel="telegram", external_id="123")
    seeded_session.add(chat)
    await seeded_session.commit()

    await deliver_outgoing(chat, "**Жирный** и *курсив*")
    assert adapter.sent == [("123", "Жирный и курсив")]
    bot_manager.clear()


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


# --- Горячее применение настроек (без перезапуска) ---


async def test_bot_manager_stop(seeded_session):
    adapter = FakeAdapter()
    bot_manager.start(adapter)
    assert bot_manager.get("telegram") is adapter
    await bot_manager.stop("telegram")
    assert bot_manager.get("telegram") is None
    bot_manager.clear()


async def test_apply_bot_config_stops_when_disabled(seeded_session):
    from app.bots.service import apply_bot_config
    from app.core.database import async_session_factory

    adapter = FakeAdapter()
    bot_manager.register(adapter)
    await apply_bot_config(async_session_factory, "telegram", enabled=False, token=None)
    assert bot_manager.get("telegram") is None
    bot_manager.clear()


async def test_admin_save_bots_applies_hot_reload(client, seeded_session):
    """Сохранение настроек в админке выключает зарегистрированного бота сразу."""
    from app.bots.service import bot_manager

    bot_manager.register(FakeAdapter())
    admin = (
        await seeded_session.execute(
            select(user_service.User).where(user_service.User.is_admin.is_(True))
        )
    ).scalars().first()
    client.cookies.set("access_token", create_access_token(str(admin.id)))

    resp = await client.post(
        "/admin/bots",
        data={"telegram_enabled": "", "telegram_name": "ТГ", "maks_enabled": "", "maks_name": ""},
    )
    assert resp.status_code == 303
    # Телеграм-бот выключен — адаптер остановлен (токен не задан).
    assert bot_manager.get("telegram") is None
    bot_manager.clear()
