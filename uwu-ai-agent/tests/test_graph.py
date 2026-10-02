"""Тесты оркестрации (графа) с фейковым клиентом ядра, без LLM и сети.

Покрывают детерминированный fallback-путь (LLM недоступен) и сериализацию
tool-calls. LLM-путь с реальными вызовами инструментов проверяется интеграционно.
"""
import pytest

from app.graph import AgentState, run_turn
from app.llm import LLM


class FakeClient:
    """Фейковый клиент ядра: пустой контекст и настраиваемый каталог."""

    def __init__(self) -> None:
        self.search_results: list[dict] = []
        self.search_calls: list[str] = []

    async def get_context(self, chat_id: int) -> dict:
        return {"customer": None, "cart": [], "history": []}

    async def search_catalog(self, query: str, limit: int = 50) -> list:
        self.search_calls.append(query)
        return self.search_results

    async def get_order_status(self, order_id: int) -> dict | None:
        return {"id": order_id, "status": "new"}


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.mark.asyncio
async def test_greeting_fallback(client):
    llm = LLM(api_key="")  # fallback-режим
    state = await run_turn(
        client, llm, {"message_id": 1, "chat_id": 7, "text": "Здравствуйте!"}
    )
    assert state.intent == "consultation"
    assert state.final_answer


@pytest.mark.asyncio
async def test_price_fallback_searches(client):
    llm = LLM(api_key="")
    state = await run_turn(
        client, llm, {"message_id": 2, "chat_id": 7, "text": "сколько стоит молоко"}
    )
    assert state.intent == "price"
    assert "search_catalog" in state.tool_calls
    assert client.search_calls == ["молоко"]


@pytest.mark.asyncio
async def test_order_status_fallback(client):
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
