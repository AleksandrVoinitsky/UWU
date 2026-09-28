"""Тесты детерминированного fallback-ответчика (без LLM)."""
from app.responder import classify_intent, detect_language, extract_query, generate


def test_detect_language():
    assert detect_language("Привет, есть ли молоко?") == "ru"
    assert detect_language("hello, do you have milk?") == "en"


def test_classify_greeting():
    assert classify_intent("Здравствуйте!") == "consultation"
    assert classify_intent("hello") == "consultation"


def test_classify_price():
    assert classify_intent("сколько стоит молоко") == "price"
    assert classify_intent("какая цена на хлеб") == "price"


def test_classify_stock():
    assert classify_intent("есть ли хлеб в наличии") == "stock"
    assert classify_intent("остаток молока") == "stock"


def test_classify_create_order():
    assert classify_intent("хочу оформить заказ") == "create_order"
    assert classify_intent("купить молоко и хлеб") == "create_order"


def test_classify_fallback():
    assert classify_intent("asdf qwerty 123") == "fallback"


def test_generate_greeting_ru():
    answer = generate(intent="consultation", text="Привет")
    assert "UWU" in answer


def test_generate_products_ru():
    products = [{"name": "Молоко 1 л", "retail_price": "78.00"}]
    answer = generate(intent="price", text="сколько стоит молоко", products=products)
    assert "Молоко" in answer


def test_generate_no_products():
    answer = generate(intent="price", text="сколько стоит молоко", products=[])
    assert "Не нашёл" in answer


def test_generate_order_status():
    order = {"id": 42, "status": "new"}
    answer = generate(intent="order_status", text="статус заказа 42", order=order)
    assert "42" in answer


def test_extract_query_strips_stopwords():
    assert extract_query("Привет! Есть ли молоко?") == "молоко"
    assert extract_query("сколько стоит хлеб") == "хлеб"
    assert extract_query("hello, do you have milk?") == "milk"
