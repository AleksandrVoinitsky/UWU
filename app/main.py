"""Точка входа FastAPI-приложения UWU.

Собирает REST API и веб-интерфейс, настраивает CORS, статику и шаблоны.
При старте выполняет идемпотентную инициализацию начальных данных.

См. также: :mod:`app.api.router`, :mod:`app.web.router`,
:mod:`app.services.seed_service`.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.database import async_session_factory
from app.services import seed_service
from app.web.router import web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация при старте: сид начальных данных."""
    async with async_session_factory() as session:
        await seed_service.seed_all(session)
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    application.include_router(api_router)
    application.include_router(web_router)

    application.mount(
        "/static", StaticFiles(directory="app/static"), name="static"
    )

    @application.get("/healthz", tags=["health"])
    async def healthz() -> dict:
        return {"status": "ok"}

    return application


app = create_app()
