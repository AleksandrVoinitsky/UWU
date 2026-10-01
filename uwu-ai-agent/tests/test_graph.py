"""Тесты оркестрации (графа) с фейковым клиентом ядра, без LLM и сети."""
import pytest

from app.graph import AgentState, retrieve_context, run_turn
from app.llm import LLM


class FakeClient:
    """Фейковый клиент ядра: возвращает пустой контекст и настраиваемый каталог."""

    def __init__(self) -> None:
        self.posted: list[str] = []
        self.marked: list[int] = []
        self.search_results: list[dict] = []
        self.search_calls: list[str] = []

    async def get_context(self, chat_id: int) -> dict:
        return {"customer": None, "cart": [], "history": []}

    async def search_catalog(self, query: str, limit: int = 50) -> list:
        self.search_calls.append(query)
        return self.search_results

    async def get_order_status(self, order_id: int) -> dict | None:
        return {"id": order_id, "status": "new"}

    async def customer_insights(self, customer_id: int) -> dict | None:
        return None


class FakeLLM:
    """Фейковый LLM: возвращает фиксированные намерение/запрос/ответ."""

    available = True

    def __init__(self, intent: str = "consultation", query: str = "молоко") -> None:
        self.intent = intent
        self.query = query

    async def classify(self, text: str) -> str:
        return self.intent

    async def extract_search_query(self, text: str) -> str:
        return self.query

    async def chat(self, messages, **kwargs) -> str:
        return "canned answer"


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


@pytest.mark.asyncio
async def test_retrieve_consultation_searches_catalog(client):
    """Консультативный запрос («посоветуй …») тоже ищет каталог через LLM-запрос."""
    client.search_results = [{"name": "Молоко 1 л", "retail_price": "78.00"}]
    llm = FakeLLM(intent="consultation", query="молоко")
    state = await retrieve_context(
        AgentState(chat_id=7, text="посоветуй что-нибудь из молочных продуктов"),
        client,
        llm,
    )
    assert "search_catalog" in state.tool_calls
    assert client.search_calls == ["молоко"]
    assert state.products == [{"name": "Молоко 1 л", "retail_price": "78.00"}]


@pytest.mark.asyncio
async def test_retrieve_fallback_uses_stopword_query(client):
    """Без LLM запрос извлекается стоп-словами (для намерения fallback)."""
    llm = LLM(api_key="")
    state = await retrieve_context(
        AgentState(chat_id=7, text="посоветуй хлеб", intent="fallback"),
        client,
        llm,
    )
    assert state.tool_calls == ["search_catalog"]
    assert client.search_calls == ["хлеб"]


@pytest.mark.asyncio
async def test_retrieve_skips_search_on_empty_query(client):
    """Чистое приветствие (нет значимых слов) не вызывает поиск каталога."""
    llm = LLM(api_key="")
    state = await retrieve_context(
        AgentState(chat_id=7, text="привет", intent="consultation"),
        client,
        llm,
    )
    assert state.tool_calls == []
