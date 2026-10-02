"""Тесты определений и исполнителя инструментов (function calling)."""
import pytest

from app.tools import TOOLS, execute_tool


class FakeCore:
    async def search_catalog(self, query: str) -> list:
        return [{"name": "Молоко", "price": "78.00"}]

    async def create_order(self, customer_phone, customer_name, items):
        return {"created": True, "order": {"id": 5}}

    async def get_stock(self, nomenklatura_id):
        return {"balance": "10", "available": "8"}


def test_tools_include_write_and_read():
    names = {t["function"]["name"] for t in TOOLS}
    assert "search_catalog" in names
    assert "get_stock" in names
    assert "add_to_cart" in names
    assert "create_order" in names
    assert "match_customer" in names
    assert "get_order_status" in names


def test_create_order_schema_requires_phone_and_items():
    create = next(t for t in TOOLS if t["function"]["name"] == "create_order")
    required = set(create["function"]["parameters"]["required"])
    assert required == {"customer_phone", "items"}


@pytest.mark.asyncio
async def test_execute_search_catalog():
    result = await execute_tool(FakeCore(), "search_catalog", {"query": "молоко"})
    assert "Молоко" in result


@pytest.mark.asyncio
async def test_execute_create_order():
    result = await execute_tool(
        FakeCore(),
        "create_order",
        {"customer_phone": "7999", "items": [{"name": "молоко", "quantity": 1}]},
    )
    assert "created" in result


@pytest.mark.asyncio
async def test_execute_unknown_tool_returns_error():
    result = await execute_tool(FakeCore(), "nope", {})
    assert "unknown tool" in result


@pytest.mark.asyncio
async def test_execute_tool_swallows_exception():
    class Broken:
        async def get_stock(self, nomenklatura_id):
            raise RuntimeError("boom")

    result = await execute_tool(Broken(), "get_stock", {"nomenklatura_id": 1})
    assert "boom" in result
