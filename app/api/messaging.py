"""API мессенджера (чаты и сообщения).

Основа для интеграции с ботами (Макс, Telegram). Пока сообщения хранятся в БД,
внешняя доставка не реализована. Аутентификация — по cookie (как веб-интерфейс).

См. также: :mod:`app.models.messaging`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user_optional
from app.models.messaging import Chat, Message
from app.models.users import User

router = APIRouter(prefix="/api/chats", tags=["messaging"])


class SendMessageRequest(BaseModel):
    text: str


async def _current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await get_current_user_optional(request, session)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


@router.get("")
async def list_chats(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(_current_user),
):
    result = await session.execute(
        select(Chat).order_by(Chat.last_message_at.desc().nullslast(), Chat.id)
    )
    chats = list(result.scalars())
    return [
        {"id": c.id, "name": c.name, "channel": c.channel, "kontragent_id": c.kontragent_id}
        for c in chats
    ]


@router.get("/{chat_id}/messages")
async def get_messages(
    chat_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(_current_user),
):
    chat = await session.get(Chat, chat_id)
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    result = await session.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.id)
    )
    messages = list(result.scalars())
    return [
        {"id": m.id, "direction": m.direction, "text": m.text, "created_at": m.created_at.isoformat()}
        for m in messages
    ]


@router.post("/{chat_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(
    chat_id: int,
    payload: SendMessageRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(_current_user),
):
    chat = await session.get(Chat, chat_id)
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    message = Message(chat_id=chat_id, direction="out", text=payload.text)
    session.add(message)
    chat.last_message_at = datetime.now(timezone.utc)
    await session.commit()

    # Если чат внешний (Telegram/MAX) — отправляем ответ через адаптер бота.
    # Канал «site» (покупатель интернет-магазина) доставляется опросом — без адаптера.
    if chat.channel in ("telegram", "maks"):
        from app.bots.service import deliver_outgoing

        await deliver_outgoing(chat, payload.text)

    return {
        "id": message.id,
        "direction": "out",
        "text": message.text,
        "created_at": message.created_at.isoformat(),
    }
