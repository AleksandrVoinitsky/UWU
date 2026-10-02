"""Инструменты (действия) агента — тонкие обёртки над REST API ядра.

Агент не выполняет бизнес-логику сам: каждый инструмент вызывает соответствующий
эндпоинт ``/api/agent/*`` ядра (см. :mod:`app.core_client`). Здесь заданы
определения инструментов в формате OpenAI function-calling и исполнитель,
который связывает имя инструмента с методом клиента.

См. также: :mod:`app.core_client`, :mod:`app.graph`.
"""
from __future__ import annotations

import json
from typing import Any

from app.core_client import CoreClient

# Определения инструментов для LLM (OpenAI-compatible function calling).
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": (
                "Поиск товаров в каталоге по названию или артикулу. Возвращает "
                "список товаров с ценой и остатком. Используй, чтобы узнать, "
                "есть ли товар и сколько он стоит."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Название или часть названия товара"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock",
            "description": "Остаток конкретного товара по его id (nomenklatura_id).",
            "parameters": {
                "type": "object",
                "properties": {
                    "nomenklatura_id": {"type": "integer", "description": "id товара"},
                },
                "required": ["nomenklatura_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "match_customer",
            "description": "Найти покупателя/контрагента по номеру телефона.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Номер телефона"},
                },
                "required": ["phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Статус и состав заявки покупателя по её номеру (id).",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "description": "id заявки"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Добавить товар в корзину покупателя.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "integer", "description": "id покупателя"},
                    "nomenklatura_id": {"type": "integer", "description": "id товара"},
                    "quantity": {"type": "number", "description": "Количество"},
                },
                "required": ["customer_id", "nomenklatura_id", "quantity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": (
                "Создать заявку покупателя (черновик заказа) по номеру телефона "
                "и списку товаров. Новый номер телефона регистрируется автоматически "
                "(создаётся аккаунт и контрагент). Если заказ не создан (created=false), "
                "прочитай поле error и уточни недостающее у покупателя."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_phone": {"type": "string", "description": "Номер телефона покупателя"},
                    "customer_name": {"type": "string", "description": "Имя покупателя (необязательно)"},
                    "items": {
                        "type": "array",
                        "description": "Список товаров для заказа",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Название товара"},
                                "quantity": {"type": "number", "description": "Количество"},
                            },
                            "required": ["name", "quantity"],
                        },
                    },
                },
                "required": ["customer_phone", "items"],
            },
        },
    },
]


async def execute_tool(client: CoreClient, name: str, args: dict[str, Any]) -> str:
    """Выполняет инструмент через клиент ядра и возвращает сериализованный результат."""
    try:
        if name == "search_catalog":
            result = await client.search_catalog(args.get("query", ""))
        elif name == "get_stock":
            result = await client.get_stock(int(args["nomenklatura_id"]))
        elif name == "match_customer":
            result = await client.match_customer(args.get("phone", ""))
        elif name == "get_order_status":
            result = await client.get_order_status(int(args["order_id"]))
        elif name == "add_to_cart":
            result = await client.add_to_cart(
                int(args["customer_id"]),
                int(args["nomenklatura_id"]),
                args["quantity"],
            )
        elif name == "create_order":
            result = await client.create_order(
                customer_phone=args.get("customer_phone", ""),
                customer_name=args.get("customer_name"),
                items=args.get("items", []),
            )
        else:
            return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001 — инструмент не должен ронять агента
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, default=str)
