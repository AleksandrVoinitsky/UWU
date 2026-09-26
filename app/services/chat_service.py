"""Чат покупателя интернет-магазина с продавцом.

Переиспользует те же модели :class:`Chat`/:class:`Message`, что и боты
(Telegram/MAX), поэтому сообщения покупателя появляются в чате продавца
единообразно. Чат создаётся лениво — при первом сообщении покупателя.

Сообщения покупателя сохраняются в БД (``direction="in"``) и видны оператору в
интерфейсе чатов; ответ оператора также пишется в ту же таблицу
(``direction="out"``). Доставка ответа на site-чат в реальном времени
(websocket/polling) намеренно не реализована здесь — покупатель забирает
сообщения через :func:`list_customer_messages`.

См. также: :mod:`app.models.messaging`, :mod:`app.models.customer`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.messaging import Chat, Message

# Канал чата покупателя (отличается от internal/telegram/maks).
CHANNEL_SITE = "site"


def _chat_name(customer: Customer) -> str:
    return customer.name or customer.phone or "Покупатель"


async def _get_customer_chat(session: AsyncSession, customer: Customer) -> Chat | None:
    result = await session.execute(
        select(Chat).where(Chat.customer_id == customer.id)
    )
    return result.scalars().first()


async def list_customer_messages(session: AsyncSession, customer: Customer) -> list[dict]:
    """Сообщения чата покупателя в хронологическом порядке (пусто, если чата нет).

    Ответы оператора (``direction="out"``) помечаются прочитанными покупателем —
    просмотр чата считается прочтением.
    """
    chat = await _get_customer_chat(session, customer)
    if chat is None:
        return []
    await session.execute(
        update(Message)
        .where(
            Message.chat_id == chat.id,
            Message.direction == "out",
            Message.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await session.commit()
    result = await session.execute(
        select(Message).where(Message.chat_id == chat.id).order_by(Message.id)
    )
    return [
        {
            "id": m.id,
            "direction": m.direction,
            "text": m.text,
            "created_at": m.created_at.isoformat(),
        }
        for m in result.scalars()
    ]


async def count_customer_unread(session: AsyncSession, customer: Customer) -> int:
    """Непрочитанные ответы оператора для покупателя."""
    chat = await _get_customer_chat(session, customer)
    if chat is None:
        return 0
    result = await session.execute(
        select(func.count())
        .select_from(Message)
        .where(
            Message.chat_id == chat.id,
            Message.direction == "out",
            Message.is_read.is_(False),
        )
    )
    return result.scalar() or 0


async def send_customer_message(
    session: AsyncSession, customer: Customer, text: str
) -> dict:
    """Сохраняет сообщение покупателя (direction=in) и обновляет время чата.

    При первом сообщении создаёт чат, который затем виден продавцу.
    """
    chat = await _get_customer_chat(session, customer)
    if chat is None:
        chat = Chat(
            name=_chat_name(customer),
            channel=CHANNEL_SITE,
            customer_id=customer.id,
        )
        session.add(chat)
        await session.flush()

    message = Message(chat_id=chat.id, direction="in", text=text)
    session.add(message)
    chat.last_message_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(message)
    return {
        "id": message.id,
        "direction": message.direction,
        "text": message.text,
        "created_at": message.created_at.isoformat(),
    }
