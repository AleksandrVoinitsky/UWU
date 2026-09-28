"""Тесты оркестрации (графа) с фейковым клиентом ядра, без LLM и сети."""
import pytest

from app.graph import run_turn
from app.llm import LLM


class FakeClient:
    """Фейковый клиент ядра: возвращает пустой контекст и пустой каталог."""

    def __init__(self) -> None:
        self.posted: list[str] = []
        self.marked: list[int] = []

    async def get_context(self, chat_id: int) -> dict:
        return {"customer": None, "cart": [], "history": []}

    async def search_catalog(self, query: str, limit: int = 50) -> list:
        return []

    async def get_order_status(self, order_id: int) -> dict | None:
        return {"id": order_id, "status": "new"}

    async def customer_insights(self, customer_id: int) -> dict | None:
        return None


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.mark.asyncio
async def test_greeting_turn(client):
    llm = LLM(api_key="")  # fallback-режим
    state = await run_turn(
        client, llm, {"message_id": 1, "chat_id": 7, "text": "Здравствуйте!"}
    )
    assert state.intent == "consultation"
    assert state.final_answer


@pytest.mark.asyncio
async def test_price_turn_without_products(client):
    llm = LLM(api_key="")
    state = await run_turn(
        client, llm, {"message_id": 2, "chat_id": 7, "text": "сколько стоит молоко"}
    )
    assert state.intent == "price"
    assert state.final_answer


@pytest.mark.asyncio
async def test_order_status_extracts_id(client):
    llm = LLM(api_key="")
    state = await run_turn(
        client, llm, {"message_id": 3, "chat_id": 7, "text": "статус заказа 42"}
    )
    assert state.intent == "order_status"
    assert state.order is not None
    assert state.order["id"] == 42


@pytest.mark.asyncio
async def test_empty_text_returns_empty(client):
    llm = LLM(api_key="")
    state = await run_turn(client, llm, {"message_id": 4, "chat_id": 7, "text": "  "})
    assert state.final_answer == ""
