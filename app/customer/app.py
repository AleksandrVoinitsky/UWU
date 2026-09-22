"""Сборка клиентского приложения покупателя.

Монтируется в основное приложение по пути ``/shop`` (в одном контейнере); на
отдельный домен выносится реверс-прокси. Переиспользует ядро (модели, сервисы,
БД) и имеет собственную аутентификацию покупателей.

См. также: :mod:`app.customer.api`, :mod:`app.customer.web`.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.customer import api, web


def create_customer_app() -> FastAPI:
    application = FastAPI(title="UWU Shop", docs_url=None, openapi_url=None, redoc_url=None)
    application.include_router(api.router)
    application.include_router(web.router)
    return application
