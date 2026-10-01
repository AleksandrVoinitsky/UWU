"""Детерминированный fallback-ответчик (без LLM).

Используется, когда LLM не сконфигурирован (нет ``LLM_API_KEY``): агент всё равно
работает «из коробки» — классифицирует намерение по ключевым словам и формирует
простой ответ на основе результатов инструментов (поиск каталога, остатки).

См. также: :mod:`app.llm`, :mod:`app.graph`.
"""
from __future__ import annotations

from typing import Any

# Категории намерений (совпадают с узлом classify_intent графа).
INTENTS = (
    "consultation",
    "stock",
    "price",
    "order_status",
    "add_to_cart",
    "create_order",
    "reorder_suggestion",
    "fallback",
)

# Ключевые слова по категориям (ru + en). Порядок важен: специфичные раньше.
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "order_status": ("статус заказ", "где мой заказ", "статус", "order status",
                     "where is my order"),
    "create_order": ("заказ", "оформи", "куп", "заказать", "хочу приобрести",
                     "order", "buy", "purchase", "checkout"),
    "add_to_cart": ("корзин", "добавь", "в корзину", "cart", "add"),
    "stock": ("наличие", "остат", "есть ли", "сколько на складе", "в наличии",
              "stock", "available", "in stock"),
    "price": ("цен", "стоит", "почём", "почем", "сколько стоит", "прайс",
              "price", "cost", "how much"),
    "reorder_suggestion": ("повтори", "докупить", "список покупок", "рекоменд",
                           "reorder", "recommend", "shopping list"),
    "consultation": ("здравств", "привет", "добрый", "помощь", "что ты умеешь",
                     "hello", "hi", "hey", "help", "start"),
}


# Стоп-слова (ru + en): приветствия, вопросительные и служебные слова, которые
# не несут смысла для поиска по каталогу.
_STOPWORDS: frozenset[str] = frozenset(
    "привет здравствуйте здравствуй добрый день добрый есть ли сколько стоит цена "
    "наличие остаток в наличии хочу нужен нужна нужно пожалуйста подскажите скажите "
    "посоветуй порекомендуй предложи покажи что что-нибудь что-то какой-нибудь "
    "можете можно какой какая какое какие и на в по с за у к от из для не а "
    "hello hi hey do you have how much price of the a an is there any in stock "
    "please i want need tell me can you show recommend".split()
)


def detect_language(text: str) -> str:
    """Грубо определяет язык сообщения: 'ru' | 'en' (по кириллице)."""
    return "ru" if any("\u0400" <= ch <= "\u04ff" for ch in text) else "en"


def extract_query(text: str) -> str:
    """Извлекает значимую строку поиска из сообщения (без стоп-слов и пунктуации).

    Используется fallback-поиском каталога: ядро ищет ``ILIKE %query%`` по
    полному названию, поэтому передавать всё сообщение целиком (с приветствием
    и вопросительными словами) неэффективно. Пустая строка — если значимых
    слов нет (чистое приветствие), тогда поиск не выполняется.
    """
    import re

    words = re.findall(r"[a-zа-яё0-9]+", text.lower())
    meaningful = [w for w in words if w not in _STOPWORDS]
    return " ".join(meaningful)


def classify_intent(text: str) -> str:
    """Классифицирует намерение по ключевым словам (fallback-классификатор)."""
    lower = text.lower()
    for intent, keywords in _KEYWORDS.items():
        if any(k in lower for k in keywords):
            return intent
    return "fallback"


def _fmt_money(value: Any) -> str:
    """Форматирует денежную величину из строки/Decimal без лишних нулей."""
    try:
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def generate(
    *,
    intent: str,
    text: str,
    products: list[dict] | None = None,
    stock: dict | None = None,
    order: dict | None = None,
) -> str:
    """Формирует детерминированный ответ по намерению и результатам инструментов."""
    lang = detect_language(text)
    products = products or []

    if lang == "ru":
        return _generate_ru(intent, products, stock, order)
    return _generate_en(intent, products, stock, order)


def _generate_ru(
    intent: str,
    products: list[dict],
    stock: dict | None,
    order: dict | None,
) -> str:
    if intent == "consultation":
        return (
            "Здравствуйте! Я консультант UWU. Подскажу по товарам, наличию и ценам, "
            "помогу собрать корзину и оформить заказ. Что вас интересует?"
        )
    if intent == "create_order":
        return (
            "С удовольствием оформлю заказ! Подскажите номер телефона и список "
            "товаров с количеством (например: «молоко 2 шт, хлеб 1 шт»)."
        )
    if intent == "add_to_cart":
        return "Назовите товар и количество — добавлю его в вашу корзину."
    if intent == "order_status":
        if order is None:
            return "Подскажите номер заказа — проверю его статус."
        return (
            f"Заказ #{order.get('id')}: статус «{order.get('status', '—')}»."
        )
    if intent == "reorder_suggestion":
        return (
            "Могу предложить список покупок на основе ваших прошлых заказов. "
            "Уточните, пожалуйста, ваш номер телефона."
        )
    if intent in ("stock", "price"):
        if stock is not None:
            return (
                f"Остаток: {_fmt_money(stock.get('balance'))}, "
                f"доступно {_fmt_money(stock.get('available'))}."
            )
        if products:
            lines = []
            for p in products[:5]:
                price = p.get("retail_price") or p.get("price")
                lines.append(
                    f"• {p.get('name')} — {_fmt_money(price) if price else 'цена по запросу'}"
                    + (f" (остаток {_fmt_money(p.get('balance'))})" if p.get("balance") else "")
                )
            return "Нашёл в каталоге:\n" + "\n".join(lines)
        return "Не нашёл такой товар. Уточните название или артикул."
    return "Извините, не совсем понял. Уточните вопрос — помогу с товарами, ценами и заказами."


def _generate_en(
    intent: str,
    products: list[dict],
    stock: dict | None,
    order: dict | None,
) -> str:
    if intent == "consultation":
        return (
            "Hello! I'm the UWU assistant. I can help with products, availability, "
            "prices, your cart and orders. How can I help?"
        )
    if intent == "create_order":
        return (
            "I'd be happy to place an order! Please tell me your phone number and "
            "the items with quantities (e.g. \"milk x2, bread x1\")."
        )
    if intent == "add_to_cart":
        return "Tell me the product and quantity, and I'll add it to your cart."
    if intent == "order_status":
        if order is None:
            return "Please tell me your order number and I'll check its status."
        return f"Order #{order.get('id')}: status «{order.get('status', '—')}»."
    if intent == "reorder_suggestion":
        return (
            "I can suggest a shopping list based on your past orders. "
            "Could you share your phone number?"
        )
    if intent in ("stock", "price"):
        if stock is not None:
            return (
                f"Balance: {_fmt_money(stock.get('balance'))}, "
                f"available {_fmt_money(stock.get('available'))}."
            )
        if products:
            lines = []
            for p in products[:5]:
                price = p.get("retail_price") or p.get("price")
                lines.append(
                    f"• {p.get('name')} — {_fmt_money(price) if price else 'price on request'}"
                )
            return "Found in catalog:\n" + "\n".join(lines)
        return "I couldn't find that product. Could you clarify the name or SKU?"
    return "Sorry, I didn't quite catch that. Ask me about products, prices or orders."
