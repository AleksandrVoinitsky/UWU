"""Тесты write-инструментов агента, персонализации и семантического поиска.

Покрывают (контракт CORE_CONTRACT.md из uwu-ai-agent):
- write-инструменты ``POST /api/agent/add_to_cart`` и ``/create_order`` (§2.9);
- персонализацию ``GET /api/agent/customer/{id}`` (§7.2);
- семантический поиск ``POST /api/agent/search_semantic`` (pgvector + fallback);
- клиент эмбеддингов (OpenAI-совместимый, юнит-тест с мок-транспортом).

См. также: :mod:`app.api.agent`, :mod:`app.services.search_service`,
:mod:`app.services.embedding_service`, :mod:`app.services.agent_service`.
"""
from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.models.catalog import Nomenklatura
from app.models.customer import Customer
from app.models.document.base_document import Document
from app.models.embeddings import EMBEDDING_DIM, NomenklaturaEmbedding
from app.models.enums import DocType
from app.services import agent_service, embedding_service, search_service
from app.services.embedding_service import EmbeddingClient


@pytest.fixture
async def agent_headers(seeded_session):
    """Заголовок авторизации с валидным API-ключом агента (полные права)."""
    _, raw = await agent_service.create_key(seeded_session, name="test-agent")
    return {"Authorization": f"Bearer {raw}"}


@pytest.fixture
async def read_only_headers(seeded_session):
    """API-ключ без права ``documents.write`` / ``reports.read``."""
    _, raw = await agent_service.create_key(
        seeded_session, name="read-only", permissions=["catalog.read"]
    )
    return {"Authorization": f"Bearer {raw}"}


@pytest.fixture
async def write_only_headers(seeded_session):
    """API-ключ с ``documents.write``, но без ``catalog.read``."""
    _, raw = await agent_service.create_key(
        seeded_session, name="write-only", permissions=["documents.write"]
    )
    return {"Authorization": f"Bearer {raw}"}


async def _make_customer(session, phone="79990000001") -> Customer:
    customer = Customer(phone=phone, password_hash="x", name="Иван")
    session.add(customer)
    await session.flush()
    return customer


async def _make_nomen(session, code, name, price="100.00") -> Nomenklatura:
    n = Nomenklatura(code=code, name=name, retail_price=Decimal(price))
    session.add(n)
    await session.flush()
    return n


# --- Write-инструменты ----------------------------------------------------------


async def test_add_to_cart(client, agent_headers, seeded_session):
    customer = await _make_customer(seeded_session)
    nomen = await _make_nomen(seeded_session, "001", "Ручка")
    await seeded_session.commit()

    resp = await client.post(
        "/api/agent/add_to_cart",
        headers=agent_headers,
        json={"customer_id": customer.id, "nomenklatura_id": nomen.id, "quantity": 2},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["items"][0]["nomenklatura_id"] == nomen.id
    assert data["items"][0]["quantity"] == 2
    assert data["total"] == "200.00"


async def test_add_to_cart_requires_write_permission(client, read_only_headers, seeded_session):
    customer = await _make_customer(seeded_session)
    nomen = await _make_nomen(seeded_session, "002", "Тетрадь")
    await seeded_session.commit()

    resp = await client.post(
        "/api/agent/add_to_cart",
        headers=read_only_headers,
        json={"customer_id": customer.id, "nomenklatura_id": nomen.id, "quantity": 1},
    )
    assert resp.status_code == 403


async def test_add_to_cart_missing_customer(client, agent_headers):
    resp = await client.post(
        "/api/agent/add_to_cart",
        headers=agent_headers,
        json={"customer_id": 9999, "nomenklatura_id": 1, "quantity": 1},
    )
    assert resp.status_code == 404


async def test_create_order_draft(client, agent_headers, seeded_session):
    customer = await _make_customer(seeded_session)
    nomen = await _make_nomen(seeded_session, "003", "Ручка", price="50.00")
    await seeded_session.commit()

    resp = await client.post(
        "/api/agent/create_order",
        headers=agent_headers,
        json={
            "customer_id": customer.id,
            "items": [{"nomenklatura_id": nomen.id, "quantity": 3}],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "draft"
    assert data["items"][0]["name"] == "Ручка"
    assert data["items"][0]["quantity"] == 3
    assert Decimal(str(data["total"])) == Decimal("150.00")

    # Документ создан как ZAKAZ в статусе DRAFT.
    doc = (await seeded_session.execute(select(Document).where(Document.id == data["id"]))).scalar_one()
    assert doc.doc_type == DocType.ZAKAZ.value
    assert doc.status == "draft"


async def test_create_order_requires_write_permission(client, read_only_headers, seeded_session):
    customer = await _make_customer(seeded_session)
    nomen = await _make_nomen(seeded_session, "004", "Карандаш")
    await seeded_session.commit()

    resp = await client.post(
        "/api/agent/create_order",
        headers=read_only_headers,
        json={"customer_id": customer.id, "items": [{"nomenklatura_id": nomen.id, "quantity": 1}]},
    )
    assert resp.status_code == 403


async def test_create_order_empty_items(client, agent_headers, seeded_session):
    customer = await _make_customer(seeded_session)
    await seeded_session.commit()

    resp = await client.post(
        "/api/agent/create_order",
        headers=agent_headers,
        json={"customer_id": customer.id, "items": []},
    )
    assert resp.status_code == 400


async def test_create_order_missing_nomen(client, agent_headers, seeded_session):
    customer = await _make_customer(seeded_session)
    await seeded_session.commit()

    resp = await client.post(
        "/api/agent/create_order",
        headers=agent_headers,
        json={"customer_id": customer.id, "items": [{"nomenklatura_id": 9999, "quantity": 1}]},
    )
    assert resp.status_code == 400


# --- Персонализация -------------------------------------------------------------


async def test_customer_insights(client, agent_headers, seeded_session):
    customer = await _make_customer(seeded_session)
    await seeded_session.commit()

    resp = await client.get(f"/api/agent/customer/{customer.id}", headers=agent_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["customer"]["name"] == "Иван"
    assert "history" in data
    assert "reorder" in data
    assert "top_items" in data
    assert "memory" in data
    assert data["memory"]["orders_count"] == 0


async def test_customer_insights_requires_reports_read(client, read_only_headers, seeded_session):
    customer = await _make_customer(seeded_session)
    await seeded_session.commit()

    resp = await client.get(f"/api/agent/customer/{customer.id}", headers=read_only_headers)
    assert resp.status_code == 403


async def test_customer_insights_missing(client, agent_headers):
    resp = await client.get("/api/agent/customer/9999", headers=agent_headers)
    assert resp.status_code == 404


# --- Семантический поиск --------------------------------------------------------


def _vec(*ones: int) -> list[float]:
    """Вектор размерности EMBEDDING_DIM с единицами на позициях ``ones``."""
    v = [0.0] * EMBEDDING_DIM
    for i in ones:
        v[i] = 1.0
    return v


async def test_search_semantic_fallback_keyword(client, agent_headers, seeded_session, monkeypatch):
    """Без провайдера эмбеддингов — fallback по ключевым словам."""
    await _make_nomen(seeded_session, "010", "Ручка гелевая")
    await seeded_session.commit()

    monkeypatch.setattr(embedding_service, "is_configured", lambda: False)

    resp = await client.post(
        "/api/agent/search_semantic",
        headers=agent_headers,
        json={"query": "ручк"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Ручка гелевая"
    assert "similarity" not in data[0]


async def test_search_semantic_vector(client, agent_headers, seeded_session, monkeypatch):
    """Векторный поиск: ближайший эмбеддинг — первым (с оценкой сходства)."""
    a = await _make_nomen(seeded_session, "011", "Ручка")
    b = await _make_nomen(seeded_session, "012", "Молоко")
    await seeded_session.flush()
    seeded_session.add(NomenklaturaEmbedding(nomenklatura_id=a.id, text="Ручка", embedding=_vec(0)))
    seeded_session.add(NomenklaturaEmbedding(nomenklatura_id=b.id, text="Молоко", embedding=_vec(1)))
    await seeded_session.commit()

    monkeypatch.setattr(embedding_service, "is_configured", lambda: True)
    monkeypatch.setattr(embedding_service, "embed_texts", _fake_embed([_vec(0)]))

    resp = await client.post(
        "/api/agent/search_semantic",
        headers=agent_headers,
        json={"query": "канцелярия", "limit": 10},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["name"] == "Ручка"
    assert data[0]["similarity"] > 0.9


async def test_search_semantic_requires_catalog_read(client, write_only_headers):
    resp = await client.post(
        "/api/agent/search_semantic",
        headers=write_only_headers,
        json={"query": "x"},
    )
    assert resp.status_code == 403


def _fake_embed(vectors):
    async def _inner(texts):
        return vectors
    return _inner


# --- Клиент эмбеддингов (юнит) --------------------------------------------------


def _embedding_transport(payload: dict) -> httpx.MockTransport:
    """MockTransport, возвращающий заранее заданный ответ /embeddings."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/embeddings"
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


async def test_embedding_client_parses_response():
    transport = _embedding_transport(
        {"data": [{"embedding": [0.1, 0.2, 0.3]}, {"embedding": [0.4, 0.5, 0.6]}]}
    )
    client = EmbeddingClient("http://emb.test", api_key="k", model="m", transport=transport)
    vectors = await client.embed_texts(["a", "b"])
    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    await client.aclose()


async def test_embedding_client_not_configured():
    client = EmbeddingClient("")
    assert not client.is_configured()
    with pytest.raises(embedding_service.EmbeddingError):
        await client.embed_texts(["x"])
    await client.aclose()


async def test_embedding_client_mismatched_count():
    transport = _embedding_transport({"data": [{"embedding": [0.1]}]})
    client = EmbeddingClient("http://emb.test", transport=transport)
    with pytest.raises(embedding_service.EmbeddingError):
        await client.embed_texts(["a", "b"])
    await client.aclose()


# --- Поиск по ключевым словам (сервис) ------------------------------------------


async def test_keyword_search_service(seeded_session):
    await _make_nomen(seeded_session, "020", "Ручка", price="10.00")
    await seeded_session.commit()

    rows = await search_service.keyword_search(seeded_session, "руч")
    assert len(rows) == 1
    assert rows[0]["name"] == "Ручка"
    assert rows[0]["price"] == "10.00"
    assert rows[0]["stock"] == "0"
