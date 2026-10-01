"""Тесты дедупликации сообщений (webhook ↔ polling) в control-plane."""
import pytest

from app.main import _claim, _process_message, _release, _to_message_id


class FakeClient:
    """Клиент ядра, записывающий публикацию ответов и пометку прочитанным."""

    def __init__(self) -> None:
        self.posted: list[tuple[int, str]] = []
        self.marked: list[int] = []

    async def get_context(self, chat_id: int) -> dict:
        return {"customer": None, "cart": [], "history": []}

    async def search_catalog(self, query: str, limit: int = 50) -> list:
        return []

    async def get_order_status(self, order_id: int) -> dict | None:
        return None

    async def customer_insights(self, customer_id: int) -> dict | None:
        return None

    async def post_message(self, chat_id: int, text: str) -> dict:
        self.posted.append((chat_id, text))
        return {}

    async def mark_inbox_read(self, message_ids: list[int]) -> dict:
        self.marked.extend(message_ids)
        return {"marked": len(message_ids)}

    async def post_run(self, **kwargs) -> dict | None:
        return None


class FakeLLM:
    available = False


def test_to_message_id():
    assert _to_message_id(5) == 5
    assert _to_message_id("7") == 7
    assert _to_message_id(None) == -1
    assert _to_message_id(-1) == -1
    assert _to_message_id(0) == -1
    assert _to_message_id("abc") == -1


@pytest.mark.asyncio
async def test_claim_and_release():
    assert await _claim(10) is True
    assert await _claim(10) is False  # уже занято
    await _release(10)
    assert await _claim(10) is True
    await _release(10)


@pytest.mark.asyncio
async def test_process_skips_already_claimed():
    """Занятое (webhook) сообщение не обрабатывается повторно polling'ом."""
    client = FakeClient()
    llm = FakeLLM()
    await _claim(99)
    try:
        await _process_message(
            client, llm, {"message_id": 99, "chat_id": 1, "text": "привет"}
        )
        assert client.posted == []  # дубль — ответ не публикуем
        assert client.marked == []
    finally:
        await _release(99)


@pytest.mark.asyncio
async def test_process_marks_read_on_success():
    client = FakeClient()
    llm = FakeLLM()
    await _process_message(
        client, llm, {"message_id": 123, "chat_id": 1, "text": "привет"}
    )
    assert len(client.posted) == 1
    assert client.marked == [123]
