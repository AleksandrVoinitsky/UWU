"""API, потребляемое AI-агентом (``/api/agent/*``).

Агент выполняется в отдельном контейнере ``uwu-ai-agent`` и обращается к ядру
через эти эндпоинты с API-key аутентификацией (см. :func:`app.core.deps.get_current_agent`).
Здесь ядро — единственный источник бизнес-логики: чтение конфигурации агента
(промпты/инструменты), обмен сообщениями, контекст покупателя, одобрения
(human-in-the-loop) и журнал запусков.

См. также: :mod:`app.services.agent_service`, :mod:`app.models.agent`,
:mod:`app.services.customer_service`, :mod:`app.services.stock_service`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.core.deps import get_current_agent
from app.models.agent import AgentApiKey, AgentApproval, AgentRun
from app.models.customer import Customer
from app.models.document.base_document import Document
from app.models.enums import DocType
from app.models.messaging import Chat, Message
from app.services import agent_service, customer_service, search_service, stock_service

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Все эндпоинты требуют валидного API-ключа агента.
AGENT = Depends(get_current_agent)


def _require_perm(key: AgentApiKey, perm: str) -> None:
    """Проверяет право инструмента по API-ключу (минимальные привилегии)."""
    if perm not in key.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


# --- Конфигурация (кэш агента) -------------------------------------------------


@router.get("/prompts")
async def list_prompts(
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Активные промпты (с текстом активной версии) — для кэша агента."""
    prompts = await agent_service.list_prompts(session)
    out = []
    for p in prompts:
        ver = await agent_service.active_template(session, p)
        out.append(
            {
                "key": p.key,
                "name": p.name,
                "description": p.description,
                "active_version": p.active_version,
                "template": ver.template if ver else "",
                "variables": ver.variables if ver else [],
            }
        )
    return out


@router.get("/tools")
async def list_tools(
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Включённые инструменты — для регистрации в LLM (tool-calling)."""
    tools = await agent_service.list_tools(session)
    return [
        {
            "key": t.key,
            "name": t.name,
            "description": t.description,
            "endpoint": t.endpoint,
            "method": t.method,
            "params_schema": t.params_schema,
            "permission": t.permission,
            "approval_policy": t.approval_policy,
            "approval_threshold_amount": (
                str(t.approval_threshold_amount)
                if t.approval_threshold_amount is not None
                else None
            ),
            "rate_limit": t.rate_limit,
        }
        for t in tools
        if t.enabled
    ]


# --- Сообщения -----------------------------------------------------------------


@router.get("/inbox")
async def inbox(
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Непрочитанные входящие сообщения (polling-режим) с контекстом чата."""
    result = await session.execute(
        select(Message, Chat)
        .join(Chat, Chat.id == Message.chat_id)
        .where(Message.direction == "in", Message.is_read.is_(False))
        .order_by(Message.id)
    )
    return [
        {
            "message_id": m.id,
            "chat_id": c.id,
            "chat_name": c.name,
            "channel": c.channel,
            "customer_id": c.customer_id,
            "text": m.text,
            "created_at": m.created_at.isoformat(),
        }
        for m, c in result.all()
    ]


class AgentMessageRequest(BaseModel):
    chat_id: int
    text: str
    author: str = "agent"
    agent_run_id: int | None = None


@router.post("/messages", status_code=status.HTTP_201_CREATED)
async def post_message(
    payload: AgentMessageRequest,
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Публикует ответ агента в чат (``direction="out"``, ``author`` по умолчанию ``agent``)."""
    chat = await session.get(Chat, payload.chat_id)
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    message = Message(
        chat_id=payload.chat_id,
        direction="out",
        text=payload.text,
        author=payload.author,
        agent_run_id=payload.agent_run_id,
    )
    session.add(message)
    chat.last_message_at = datetime.now(timezone.utc)
    await session.commit()

    # Внешний канал (Telegram/MAX) — доставляем ответ через адаптер бота.
    if chat.channel in ("telegram", "maks"):
        from app.bots.service import deliver_outgoing

        await deliver_outgoing(chat, payload.text)

    return {
        "id": message.id,
        "direction": "out",
        "author": message.author,
        "text": message.text,
        "created_at": message.created_at.isoformat(),
    }


@router.get("/context/{chat_id}")
async def context(
    chat_id: int,
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Сводка контекста покупателя: чат, профиль, корзина и последние сообщения."""
    chat = await session.get(Chat, chat_id)
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    customer = None
    cart: list[dict] = []
    if chat.customer_id is not None:
        customer = await session.get(Customer, chat.customer_id)
        if customer is not None:
            cart = await customer_service.get_cart_items(session, customer.id)

    recent = (
        await session.execute(
            select(Message).where(Message.chat_id == chat_id).order_by(Message.id.desc()).limit(20)
        )
    ).scalars().all()

    return {
        "chat": {
            "id": chat.id,
            "name": chat.name,
            "channel": chat.channel,
            "agent_enabled": chat.agent_enabled,
        },
        "customer": {"id": customer.id, "name": customer.name} if customer else None,
        "cart": cart,
        "history": [
            {
                "id": m.id,
                "direction": m.direction,
                "author": m.author,
                "text": m.text,
                "created_at": m.created_at.isoformat(),
            }
            for m in reversed(recent)
        ],
    }


# --- Одобрения (human-in-the-loop) ---------------------------------------------


class ApprovalCreate(BaseModel):
    tool_key: str
    payload: dict = {}
    chat_id: int | None = None
    customer_id: int | None = None
    run_id: int | None = None


@router.post("/approvals", status_code=status.HTTP_201_CREATED)
async def create_approval(
    payload: ApprovalCreate,
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Создаёт запрос одобрения действия (агент прерывает граф и ждёт решения)."""
    approval = AgentApproval(
        tool_key=payload.tool_key,
        payload=payload.payload,
        chat_id=payload.chat_id,
        customer_id=payload.customer_id,
        run_id=payload.run_id,
        status="pending",
        resume_value={},
    )
    session.add(approval)
    await session.commit()
    await session.refresh(approval)
    return {
        "id": approval.id,
        "tool_key": approval.tool_key,
        "status": approval.status,
    }


@router.get("/approvals/{approval_id}")
async def get_approval(
    approval_id: int,
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Статус одобрения (агент опрашивает для возобновления графа)."""
    approval = await session.get(AgentApproval, approval_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")
    return {
        "id": approval.id,
        "tool_key": approval.tool_key,
        "status": approval.status,
        "resume_value": approval.resume_value,
        "decided_by": approval.decided_by,
        "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
    }


# --- Журнал запусков -----------------------------------------------------------


class RunCreate(BaseModel):
    trace_id: str
    chat_id: int | None = None
    customer_id: int | None = None
    intent: str | None = None
    prompt_versions: dict = {}
    tool_calls: list = []
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    model: str | None = None
    status: str = "ok"
    error: str | None = None


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: RunCreate,
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Пишет результат запуска агента в журнал (аудит/трассировка)."""
    run = AgentRun(**payload.model_dump())
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return {"id": run.id, "trace_id": run.trace_id}


# --- Tool-friendly чтение (обёртки над REST-эндпоинтами ядра) -------------------


@router.get("/search_catalog")
async def search_catalog(
    query: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Поиск товаров по названию/артикулу (с остатком и ценой)."""
    _require_perm(key, "catalog.read")
    return await search_service.keyword_search(session, query, limit=50)


@router.get("/get_stock")
async def get_stock(
    nomenklatura_id: int,
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Остаток товара: учётный и доступный (учёт − резерв)."""
    _require_perm(key, "catalog.read")
    balance = await stock_service.get_balance(session, nomenklatura_id)
    available = await stock_service.get_available(session, nomenklatura_id)
    return {
        "nomenklatura_id": nomenklatura_id,
        "balance": str(balance),
        "available": str(available),
    }


@router.get("/get_cart")
async def get_cart(
    customer_id: int,
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Текущая корзина покупателя (позиции с названиями и суммой)."""
    _require_perm(key, "catalog.read")
    items = await customer_service.get_cart_items(session, customer_id)
    total = await customer_service.cart_total(session, customer_id)
    return {"customer_id": customer_id, "items": items, "total": str(total)}


@router.get("/get_zakaz")
async def get_zakaz(
    order_id: int,
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Статус и состав заявки покупателя (ZAKAZ)."""
    _require_perm(key, "documents.read")
    result = await session.execute(
        select(Document)
        .options(selectinload(Document.items))
        .where(Document.id == order_id, Document.doc_type == DocType.ZAKAZ.value)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return await customer_service.order_context(session, doc)


# --- Tool-friendly запись (выполняется после одобрения оператора) ---------------


class AddToCartRequest(BaseModel):
    customer_id: int
    nomenklatura_id: int
    quantity: Decimal


class OrderItemRequest(BaseModel):
    nomenklatura_id: int
    quantity: Decimal


class CreateOrderRequest(BaseModel):
    customer_id: int
    items: list[OrderItemRequest]


@router.post("/add_to_cart", status_code=status.HTTP_201_CREATED)
async def agent_add_to_cart(
    payload: AddToCartRequest,
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Добавляет товар в корзину покупателя (после одобрения оператора).

    Право — ``documents.write`` (проверяется по API-ключу). Бизнес-логику
    выполняет ядро (:func:`app.services.customer_service.add_to_cart`), агент
    её не дублирует.
    """
    _require_perm(key, "documents.write")
    customer = await session.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    try:
        await customer_service.add_to_cart(
            session, payload.customer_id, payload.nomenklatura_id, payload.quantity
        )
    except customer_service.CustomerError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    items = await customer_service.get_cart_items(session, payload.customer_id)
    total = await customer_service.cart_total(session, payload.customer_id)
    return {"customer_id": payload.customer_id, "items": items, "total": str(total)}


@router.post("/create_order", status_code=status.HTTP_201_CREATED)
async def agent_create_order(
    payload: CreateOrderRequest,
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Создаёт заявку покупателя (ZAKAZ) в статусе DRAFT (после одобрения).

    Право — ``documents.write``. Позиции передаются как
    ``[{nomenklatura_id, quantity}]``; цены и ставки НДС ядро берёт из
    номенклатуры. Проведение документа остаётся за оператором.
    """
    _require_perm(key, "documents.write")
    customer = await session.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    try:
        doc = await customer_service.create_draft_order(
            session,
            customer,
            [i.model_dump() for i in payload.items],
            source="agent",
        )
    except customer_service.CustomerError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return await customer_service.order_context(session, doc)


# --- Персонализация (история / рекомендации / память) ----------------------------


@router.get("/customer/{customer_id}")
async def customer_insights(
    customer_id: int,
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Сводка покупателя для персонализации (промпт ``reorder_suggestion``).

    Возвращает профиль, историю покупок, рекомендации к заказу и «память»
    (любимые категории). Право — ``reports.read`` (аналитика по продажам).
    """
    _require_perm(key, "reports.read")
    insights = await agent_service.customer_insights(session, customer_id)
    if insights is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return insights


# --- Семантический поиск по каталогу (RAG) -------------------------------------


class SemanticSearchRequest(BaseModel):
    query: str
    limit: int = 10


@router.post("/search_semantic")
async def search_semantic(
    payload: SemanticSearchRequest,
    session: AsyncSession = Depends(get_session),
    key: AgentApiKey = AGENT,
):
    """Семантический поиск товаров (pgvector + эмбеддинги) с fallback по словам.

    Право — ``catalog.read``. Возвращает релевантные товары с остатком и ценой
    (и оценкой сходства ``similarity`` для векторного поиска).
    """
    _require_perm(key, "catalog.read")
    limit = max(1, min(payload.limit, 50))
    return await search_service.search_semantic(session, payload.query.strip(), limit)
