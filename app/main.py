"""Точка входа FastAPI-приложения UWU.

Собирает REST API и веб-интерфейс, настраивает статику, шаблоны и логирование.
При старте выполняет идемпотентную инициализацию начальных данных.

См. также: :mod:`app.api.router`, :mod:`app.web.router`,
:mod:`app.core.logging`, :mod:`app.services.seed_service`.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.database import async_session_factory
from app.core.logging import get_logger, setup_logging
from app.services import seed_service
from app.web.router import web_router

# Настраиваем логирование до создания приложения (важно для тестов и сида).
setup_logging(settings.log_level.upper())
logger = get_logger("app.main")

# Пути, которые не логируем как запросы (шум: статика и health-чеки).
_SKIP_REQUEST_LOG_PREFIXES = ("/static", "/uploads", "/healthz")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация при старте: сид начальных данных."""
    logger.info("Starting application '%s'", settings.app_name)
    async with async_session_factory() as session:
        await seed_service.seed_all(session)
    logger.info("Application started")
    yield
    logger.info("Application shutting down")


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

    # Каталог загружаемых изображений (volume в Docker).
    from pathlib import Path

    uploads = Path(settings.uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)
    application.mount(
        "/uploads", StaticFiles(directory=str(uploads)), name="uploads"
    )

    @application.middleware("http")
    async def log_requests(request: Request, call_next):
        """Логирует метод, путь, статус и длительность каждого запроса."""
        path = request.url.path
        skip = any(path.startswith(p) for p in _SKIP_REQUEST_LOG_PREFIXES)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled exception on %s %s", request.method, path
            )
            raise
        if not skip:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "%s %s -> %d (%.1f ms)",
                request.method,
                path,
                response.status_code,
                elapsed_ms,
            )
        return response

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """Единая точка обработки необработанных ошибок: логируем и отдаём 500."""
        logger.exception(
            "Unhandled error on %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    @application.get("/healthz", tags=["health"])
    async def healthz() -> dict:
        return {"status": "ok"}

    return application


app = create_app()
