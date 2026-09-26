"""Точка входа FastAPI-приложения UWU.

Собирает REST API и веб-интерфейс, настраивает статику, шаблоны и логирование.
При старте выполняет идемпотентную инициализацию начальных данных.

См. также: :mod:`app.api.router`, :mod:`app.web.router`,
:mod:`app.core.logging`, :mod:`app.services.seed_service`.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

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

# Методы, меняющие состояние (для CSRF-проверки same-origin).
_CSRF_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def _csrf_failed(request: Request) -> bool:
    """Проверяет same-origin для state-changing запросов (защита от CSRF).

    Cookie-аутентифицированные эндпоинты уязвимы к CSRF: браузер автоматически
    прикладывает cookie к cross-site запросу. Проверяем, что ``Origin``/``Referer``
    совпадают с ``Host``; если заголовок отсутствует (небраузерный клиент) — не
    блокируем, т.к. такие клиенты не прикладывают cookie автоматически.
    """
    host = request.headers.get("host")
    origin = request.headers.get("origin")
    if origin:
        origin_host = urlparse(origin).netloc
        return bool(origin_host and host and origin_host != host)
    referer = request.headers.get("referer")
    if referer:
        referer_host = urlparse(referer).netloc
        return bool(referer_host and host and referer_host != host)
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация при старте: проверка настроек, сид, запуск ботов."""
    logger.info("Starting application '%s'", settings.app_name)
    from app.core.security import validate_security_settings

    validate_security_settings()
    async with async_session_factory() as session:
        await seed_service.seed_all(session)

    # Запуск ботов мессенджеров (Telegram/MAX) в фоновых задачах.
    from app.bots.service import start_bots, stop_bots

    await start_bots(async_session_factory)

    logger.info("Application started")
    yield

    await stop_bots()
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

    # Клиентский сайт покупателя (отдельная ветвь процесса, свой домен).
    from app.customer import create_customer_app

    application.mount("/shop", create_customer_app())

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

    @application.middleware("http")
    async def csrf_protect(request: Request, call_next):
        """Защита от CSRF для cookie-аутентифицированных state-changing запросов."""
        if request.method in _CSRF_METHODS and _csrf_failed(request):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF check failed"},
            )
        return await call_next(request)

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
    async def healthz() -> JSONResponse:
        """Проверка готовности: отдаёт ok только при доступной БД."""
        try:
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 — healthcheck обязан не падать
            logger.warning("Healthcheck failed: %s", exc)
            return JSONResponse(status_code=503, content={"status": "unhealthy"})
        return JSONResponse({"status": "ok"})

    return application


app = create_app()
